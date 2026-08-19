import Link from "next/link";

export function PolicyLayout({ title, eyebrow, updated, children }: { title: string; eyebrow: string; updated: string; children: React.ReactNode }) {
  return <main className="policy-page">
    <header className="site-header policy-header"><Link className="brand" href="/" aria-label="Social Intelligence home"><span className="brand-mark" aria-hidden="true"><i /><i /><i /></span><span><b>Social Intelligence</b><small>Signal operating system</small></span></Link><Link className="button button-secondary" href="/">Back to product</Link></header>
    <article className="policy-card"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="policy-updated">Last updated: {updated}</p>{children}<footer className="policy-footer"><Link href="/privacy">Privacy</Link><Link href="/terms">Terms</Link><Link href="/data-deletion">Data deletion</Link><span>Questions? Contact the product owner through the email registered in Meta.</span></footer></article>
  </main>;
}
