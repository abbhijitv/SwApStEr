import Link from "next/link";
import {AccountNav} from '../components/account-nav';
import { Globe2, ArrowLeft, Bot, ShieldCheck } from "lucide-react";

export default function B2BPage() {
  return (
    <main className="min-h-screen bg-slate-50 px-6 py-12 text-slate-900">
      <div className="mx-auto max-w-5xl">
        <div className="business-account-nav"><AccountNav/></div>
        <Link href="/" className="inline-flex items-center gap-2 text-blue-600">
          <ArrowLeft size={18} /> Back to SwApStEr
        </Link>

        <div className="mt-16">
          <Globe2 size={44} className="text-violet-600" />

          <h1 className="mt-6 text-5xl font-extrabold">
            SwApStEr Business
          </h1>

          <p className="mt-6 max-w-2xl text-lg text-slate-600">
            AI-powered international sourcing and supplier negotiation.
            Set your requirements, compare quotations, and approve
            agreements before committing.
          </p>

          <div className="mt-12 grid gap-5 md:grid-cols-2">
            <div className="rounded-2xl border bg-white p-7">
              <Bot className="mb-4 text-violet-600" size={30} />
              <h2 className="text-xl font-semibold">AI Negotiation</h2>
              <p className="mt-3 text-slate-600">
                Buyer and supplier agents negotiate within
                their owners' authorized limits.
              </p>
            </div>

            <div className="rounded-2xl border bg-white p-7">
              <ShieldCheck className="mb-4 text-violet-600" size={30} />
              <h2 className="text-xl font-semibold">Human Approval</h2>
              <p className="mt-3 text-slate-600">
                Final agreements require explicit approval.
              </p>
            </div>
          </div>

          <p className="mt-10 text-sm text-slate-500">
            Prototype interface. Supplier interactions are not connected yet.
          </p>
        </div>
      </div>
    </main>
  );
}
