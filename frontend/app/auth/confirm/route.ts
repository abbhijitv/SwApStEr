import type {NextRequest} from 'next/server';
import {completeAuth} from '../../../lib/auth/callback';
export function GET(request: NextRequest) {return completeAuth(request, 'token');}
