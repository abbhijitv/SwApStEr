import Link from "next/link";
import {AccountNav} from './components/account-nav';
import { ArrowRight, ShoppingBag, Globe2, Bot } from "lucide-react";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-slate-50 text-slate-900">
      <div className="mx-auto max-w-6xl px-6 py-8">
        <header className="flex items-center justify-between">
          <Link href="/" className="text-2xl font-black">
            SwApStEr <span className="text-blue-600">AI</span>
          </Link>

          <AccountNav/>
        </header>

        <section className="py-20 text-center">
          <Bot size={44} className="mx-auto mb-6 text-blue-600" />

          <h1 className="text-5xl font-extrabold tracking-tight md:text-7xl">
            Better deals.
            <span className="block text-blue-600">
              Powered by AI.
            </span>
          </h1>

          <p className="mx-auto mt-6 max-w-2xl text-lg text-slate-600">
            Buy, sell, and source products with AI negotiation agents.
            You set the limits. Your AI negotiates.
            You approve the final deal.
          </p>
        </section>

        <section className="grid gap-6 md:grid-cols-2">
          <Link
            href="/marketplace"
            className="rounded-3xl border bg-white p-10 shadow-sm transition hover:shadow-xl"
          >
            <ShoppingBag size={36} className="mb-6 text-blue-600" />

            <h2 className="text-3xl font-bold">Local Marketplace</h2>

            <p className="mt-4 text-slate-600">
              Buy, sell, and rent products locally.
              Let AI agents negotiate while respecting
              your private price limits.
            </p>

            <div className="mt-8 flex items-center gap-2 font-semibold text-blue-600">
              Explore Marketplace <ArrowRight size={20} />
            </div>
          </Link>

          <Link
            href="/b2b"
            className="rounded-3xl border bg-white p-10 shadow-sm transition hover:shadow-xl"
          >
            <Globe2 size={36} className="mb-6 text-violet-600" />

            <h2 className="text-3xl font-bold">B2B Procurement</h2>

            <p className="mt-4 text-slate-600">
              Source products internationally, compare supplier quotes,
              and negotiate across languages using AI assistance.
            </p>

            <div className="mt-8 flex items-center gap-2 font-semibold text-violet-600">
              Explore Business <ArrowRight size={20} />
            </div>
          </Link>
        </section>
      </div>
    </main>
  );
}
