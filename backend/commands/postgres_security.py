"""Read-only PostgreSQL catalogs only; never inspect records.data or policy text."""
from sqlalchemy import text

TABLE_PRIVILEGES = ('SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER')
SEQUENCE_PRIVILEGES = ('USAGE','SELECT','UPDATE')


def security_report(connection):
    table = connection.execute(text("""
        SELECT c.oid, c.relrowsecurity AS rls_enabled,
               c.relforcerowsecurity AS rls_forced,
               c.relowner = (SELECT oid FROM pg_roles WHERE rolname=current_user) AS owner,
               (SELECT rolbypassrls OR rolsuper FROM pg_roles WHERE rolname=current_user) AS bypass_rls,
               current_schema()='public' AND to_regclass('records')=to_regclass('public.records') AS resolves_public,
               has_schema_privilege(current_user,'public','USAGE') AS schema_usage,
               has_schema_privilege(current_user,'public','CREATE') AS schema_create,
               (SELECT count(*) FROM pg_policy WHERE polrelid=c.oid) AS policy_count,
               (SELECT count(*) FROM pg_trigger WHERE tgrelid=c.oid AND NOT tgisinternal) AS trigger_count
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relname='records' AND c.relkind='r'
    """)).mappings().one_or_none()
    if table is None:
        return {'records':'missing', 'review_required':True}
    oid = table['oid']
    report = {key:table[key] for key in ('rls_enabled','rls_forced','owner','bypass_rls','resolves_public','schema_usage','schema_create','policy_count','trigger_count')}
    sequence = connection.scalar(text("SELECT pg_get_serial_sequence('public.records','id')"))
    report['sequence_present'] = sequence is not None
    roles = ['current_user','anon','authenticated']
    privileges = {}
    for role in roles:
        exists = role == 'current_user' or bool(connection.scalar(text('SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:role)'), {'role':role}))
        if not exists:
            privileges[role] = {'role_present':False}
            continue
        role_sql = 'current_user' if role == 'current_user' else ':role'
        access = {'role_present':True}
        access['schema'] = {p:bool(connection.scalar(text(f"SELECT has_schema_privilege({role_sql}, 'public', :privilege)"), {'role':role,'privilege':p})) for p in ('USAGE','CREATE')}
        access['table'] = {p:bool(connection.scalar(text(f'SELECT has_table_privilege({role_sql}, :oid, :privilege)'), {'role':role,'oid':oid,'privilege':p})) for p in TABLE_PRIVILEGES}
        # Column SELECT/INSERT/UPDATE grants can permit access even when table-wide grants are absent.
        access['any_column'] = {p:bool(connection.scalar(text(f'SELECT has_any_column_privilege({role_sql}, :oid, :privilege)'), {'role':role,'oid':oid,'privilege':p})) for p in ('SELECT','INSERT','UPDATE','REFERENCES')}
        access['sequence'] = {p:bool(connection.scalar(text(f'SELECT has_sequence_privilege({role_sql}, :sequence, :privilege)'), {'role':role,'sequence':sequence,'privilege':p})) if sequence else False for p in SEQUENCE_PRIVILEGES}
        privileges[role] = access
    report['privileges'] = privileges
    # Relevant default ACLs, not object payloads. Include every creator (anonymized),
    # PUBLIC, direct API-role grants and grants to roles those API roles inherit.
    defaults = connection.execute(text("""
        SELECT d.defaclrole AS creator_oid, d.defaclnamespace=0 AS global_scope,
               d.defaclobjtype AS object_type, x.grantee=0 AS public_grant,
               CASE WHEN x.grantee=0 THEN false ELSE EXISTS (
                 SELECT 1 FROM pg_roles api WHERE api.rolname IN ('anon','authenticated')
                 AND pg_has_role(api.oid,x.grantee,'USAGE')) END AS api_inherited,
               x.privilege_type
        FROM pg_default_acl d
        CROSS JOIN LATERAL aclexplode(d.defaclacl) x
        WHERE d.defaclobjtype IN ('r','S')
          AND (d.defaclnamespace=0 OR d.defaclnamespace='public'::regnamespace)
        ORDER BY d.defaclrole,d.defaclnamespace,d.defaclobjtype,x.privilege_type
    """)).mappings().all()
    creator_labels = {}
    exposed_defaults = []
    for row in defaults:
        if row['public_grant'] or row['api_inherited']:
            creator = creator_labels.setdefault(row['creator_oid'], f'creator_{len(creator_labels)+1}')
            exposed_defaults.append({'creator':creator,'scope':'global' if row['global_scope'] else 'public',
                                     'object':'table' if row['object_type']=='r' else 'sequence',
                                     'grantee':'PUBLIC' if row['public_grant'] else 'API role or inherited role',
                                     'privilege':row['privilege_type']})
    report['future_public_grants'] = exposed_defaults
    report['enabled_event_trigger_count'] = int(connection.scalar(text("SELECT count(*) FROM pg_event_trigger WHERE evtenabled <> 'D'")))
    api_exposure = any(not privileges[role].get('role_present') or any(privileges[role].get(group,{}).values()) for role in ('anon','authenticated') for group in ('table','any_column','sequence'))
    current = privileges['current_user']
    report['current_role_crud_grants'] = report['schema_usage'] and all(current['table'][p] for p in ('SELECT','INSERT','UPDATE','DELETE')) and bool(current['sequence']['USAGE'] or current['sequence']['UPDATE'])
    report['review_required'] = bool(api_exposure or exposed_defaults or not report['rls_enabled'] or not report['resolves_public'] or not report['current_role_crud_grants'] or any(privileges[role].get('schema',{}).get('CREATE',False) for role in ('anon','authenticated')))
    report['limitations'] = 'Catalog grants do not prove RLS row access, REST exposure, function safety, future creator coverage or event-trigger behavior.'
    return report
