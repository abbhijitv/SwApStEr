import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = {title:'SwApStEr | Your campus. Your deals. Your AI negotiator.',description:'A student marketplace where independent personal agents negotiate academic essentials. Your constraints stay private. You make the final call.'};
export default function RootLayout({children}:{children:React.ReactNode}) { return <html lang="en"><body>{children}</body></html> }
