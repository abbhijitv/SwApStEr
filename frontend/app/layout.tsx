import type { Metadata } from 'next';
import './globals.css';
import {AuthProvider} from './components/auth-provider';
export const metadata: Metadata = {title:'SwApStEr | Better deals, powered by AI',description:'Buy, sell, and rent with independent AI agents. Your constraints stay private. You make the final call.'};
export default function RootLayout({children}:{children:React.ReactNode}) { return <html lang="en"><body><AuthProvider>{children}</AuthProvider></body></html> }
