"""Isolated local-only integration runner. Uses synthetic Auth and temporary SQLite.

Run from the repository root: .venv/bin/python frontend/tests/support/run-account-marketplace.py
"""
import os, shutil, signal, socket, subprocess, tempfile, time
from pathlib import Path
import httpx
root=Path(__file__).resolve().parents[3]
(root/"artifacts/setup").mkdir(parents=True,exist_ok=True)
processes=[]
logs=[]
with tempfile.TemporaryDirectory(prefix="swapster-auth-ui-") as temporary:
    temp=Path(temporary)
    try:
        for port in (3101,3102,8101,55421):
            with socket.socket() as sock:
                if sock.connect_ex(("127.0.0.1",port))==0: raise RuntimeError(f"Port {port} occupied; leaving its process untouched")
        copies=[]
        for name in ("configured","unconfigured"):
            target=temp/name
            shutil.copytree(root/"frontend",target,ignore=shutil.ignore_patterns("node_modules",".next",".env.local","*.tsbuildinfo","test-results","playwright-report"))
            (target/"node_modules").symlink_to(root/"frontend/node_modules",target_is_directory=True)
            copies.append(target)
        env=dict(os.environ,PATH="/opt/homebrew/opt/node@22/bin:"+os.environ["PATH"],DATABASE_URL="sqlite:///"+str(temp/"test.db"),APP_ENV="development",AI_PROVIDER="mock",ENABLE_ACCOUNT_MARKETPLACE="true",SUPABASE_URL="http://localhost:55421",SUPABASE_PUBLISHABLE_KEY="sb_publishable_synthetic-only",SUPABASE_AUTH_LEGACY_HS256="true",NEXT_PUBLIC_SUPABASE_URL="http://localhost:55421",NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY="sb_publishable_synthetic-only",NEXT_PUBLIC_API_URL="http://localhost:8101",PLAYWRIGHT_BASE_URL="http://localhost:3101",AUTH_TEST_SERVICE_URL="http://localhost:55421",AUTH_TEST_UNCONFIGURED_URL="http://localhost:3102")
        jobs=[("mock",[str(root/".venv/bin/python"),str(root/"frontend/tests/support/mock-auth-service.py"),"55421"],env),("backend",[str(root/".venv/bin/uvicorn"),"backend.main:app","--host","127.0.0.1","--port","8101"],env)]
        for name,port,target in zip(("configured","unconfigured"),(3101,3102),copies):
            settings=dict(env)
            if name=="unconfigured": settings.update(NEXT_PUBLIC_SUPABASE_URL="",NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY="")
            jobs.append((name,["node",str(root/"frontend/node_modules/next/dist/bin/next"),"dev","--webpack","--hostname","localhost","--port",str(port),str(target)],settings))
        for name,command,settings in jobs:
            log=open(root/f"artifacts/setup/account3c2-{name}.log","w"); logs.append(log)
            processes.append(subprocess.Popen(command,cwd=root,env=settings,stdout=log,stderr=subprocess.STDOUT,start_new_session=True))
        with httpx.Client(timeout=60,trust_env=False) as client:
            for url in ("http://localhost:55421/health","http://localhost:8101/health","http://localhost:3101/login","http://localhost:3102/signup"):
                for attempt in range(60):
                    try:
                        response=client.get(url); response.raise_for_status(); print(url,"ready",flush=True); break
                    except httpx.HTTPError:
                        if any(p.poll() is not None for p in processes): raise RuntimeError("Temporary server exited; see ignored setup logs")
                        time.sleep(.5)
                else: raise RuntimeError("Server readiness timeout")
        subprocess.run(["npm","run","test:e2e","--prefix","frontend","--","tests/account-marketplace.spec.ts","tests/account-marketplace-api.spec.ts","tests/negotiation-runner.spec.ts","tests/auth-ui.spec.ts","tests/auth-callback.spec.ts","tests/supabase-foundation.spec.ts"],cwd=root,env=env,check=True)
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGTERM)
                try: process.wait(timeout=8)
                except subprocess.TimeoutExpired: os.killpg(process.pid,signal.SIGKILL); process.wait()
        for log in logs: log.close()
        print("Temporary Auth service, backend, frontend copies, and SQLite database cleaned up",flush=True)
