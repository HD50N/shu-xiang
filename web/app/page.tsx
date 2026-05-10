import Link from "next/link";

export default function Home() {
  return (
    <div className="min-h-screen relative overflow-x-hidden" style={{ background: "var(--bg)" }}>
      <div
        className="fixed top-0 left-1/2 -translate-x-1/2 w-[900px] h-[500px] pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse at center top, rgba(201,164,71,0.07) 0%, transparent 65%)",
        }}
      />

      <nav
        className="relative z-10 flex items-center justify-between px-8 py-5"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <span className="font-display text-xl italic" style={{ color: "var(--cream)" }}>
          Shu-Xiang
        </span>
        <div
          className="text-xs tracking-widest uppercase px-3 py-1 rounded-full"
          style={{
            color: "var(--gold)",
            border: "1px solid var(--gold-border)",
            background: "var(--gold-glow)",
            fontFamily: "var(--font-body)",
          }}
        >
          Illinois LLC · Beta
        </div>
      </nav>

      <section className="relative z-10 max-w-6xl mx-auto px-8 pt-20 pb-10">
        <div className="flex items-start gap-2 mb-10">
          <div className="mt-2.5 h-px w-10 shrink-0" style={{ background: "var(--gold)" }} />
          <span
            className="text-xs tracking-[0.25em] uppercase"
            style={{ color: "var(--gold)", fontFamily: "var(--font-body)" }}
          >
            Multilingual LLC Filing
          </span>
        </div>

        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-12">
          <div>
            <h1
              className="font-display text-[clamp(3.5rem,8vw,6.5rem)] leading-[1.0] mb-8"
              style={{ color: "var(--cream)" }}
            >
              Your language.
              <br />
              Their forms.
              <br />
              <em style={{ color: "var(--gold)" }}>Our agent.</em>
            </h1>
            <p
              className="text-lg max-w-md leading-relaxed"
              style={{ color: "var(--text-dim)", fontFamily: "var(--font-body)" }}
            >
              Describe your business in your native language. Our AI agent plans the filing
              with you first, then navigates the English government filing system with the
              right context already in hand.
            </p>
            <div className="mt-10 flex flex-wrap gap-3">
              <Link
                href="/plan"
                className="relative inline-flex items-center justify-center rounded-full px-7 py-4 font-display text-xl italic overflow-hidden group"
                style={{ background: "var(--gold)", color: "var(--bg)" }}
              >
                <span
                  className="absolute inset-0 translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-700"
                  style={{ background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.18), transparent)" }}
                />
                <span className="relative">Start planning</span>
              </Link>
              <a
                href="#how-it-works"
                className="inline-flex items-center justify-center rounded-full px-7 py-4 text-sm font-medium"
                style={{
                  border: "1px solid var(--border-bright)",
                  color: "var(--text)",
                  background: "var(--bg-card)",
                }}
              >
                See how it works
              </a>
            </div>
          </div>

          <div
            className="shrink-0 w-36 h-36 rounded-full flex-col items-center justify-center text-center hidden lg:flex"
            style={{
              border: "1px solid var(--gold-border)",
              background: "var(--gold-glow)",
            }}
          >
            <div className="font-display text-3xl italic mb-1" style={{ color: "var(--gold)" }}>
              11
            </div>
            <div
              className="text-xs tracking-widest uppercase"
              style={{ color: "var(--text-dim)", fontFamily: "var(--font-body)" }}
            >
              Languages
            </div>
            <div
              className="text-xs mt-1"
              style={{ color: "var(--text-muted)", fontFamily: "var(--font-body)" }}
            >
              Free · 3 min
            </div>
          </div>
        </div>
      </section>

      <section id="how-it-works" className="relative z-10" style={{ borderTop: "1px solid var(--border)" }}>
        <div className="max-w-6xl mx-auto px-8 py-16 grid grid-cols-1 sm:grid-cols-3 gap-12">
          {[
            {
              num: "01",
              title: "Speak your language",
              body: "Describe your business in one sentence. Name, address, ownership — the agent extracts everything it can.",
            },
            {
              num: "02",
              title: "Build the plan",
              body: "The planning room turns your answers into a filing packet before the official form opens.",
            },
            {
              num: "03",
              title: "Agent fills the form",
              body: "The guided filing flow uses that packet, asks only missing details, and explains every decision.",
            },
          ].map(({ num, title, body }) => (
            <div key={num} className="flex gap-5">
              <div
                className="font-display text-4xl italic shrink-0 leading-none mt-1"
                style={{ color: "var(--gold)", opacity: 0.5 }}
              >
                {num}
              </div>
              <div>
                <div className="font-display text-xl mb-2" style={{ color: "var(--cream)" }}>
                  {title}
                </div>
                <div
                  className="text-sm leading-relaxed"
                  style={{ color: "var(--text-dim)", fontFamily: "var(--font-body)" }}
                >
                  {body}
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <footer
        className="relative z-10 px-8 py-5 flex items-center justify-between"
        style={{
          borderTop: "1px solid var(--border)",
          fontFamily: "var(--font-body)",
        }}
      >
        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
          Shu-Xiang
        </span>
        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
          Illinois Secretary of State · Frontend planning demo
        </span>
      </footer>
    </div>
  );
}
