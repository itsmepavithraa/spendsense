import Link from "next/link";

export const metadata = { title: "Privacy notice · SpendSense" };

const H2 = "mt-8 text-lg font-semibold";
const P = "mt-2 text-sm leading-relaxed text-muted";

// Plain-language privacy notice. Review it with a lawyer before promoting the site widely.
export default function Privacy() {
  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      <Link href="/" className="text-sm text-muted hover:text-ink">
        ← SpendSense
      </Link>
      <h1 className="mt-3 text-2xl font-semibold">Privacy notice</h1>
      <p className={P}>
        SpendSense is a student-built project that analyses bank statements you upload. This page says exactly what it
        stores and what you can do about it. It is a prototype, not a regulated financial product.
      </p>

      <h2 className={H2}>What we store</h2>
      <ul className={`${P} list-disc space-y-1 pl-5`}>
        <li>Your name, your email address and a one-way scrambled form (hash) of your password. We never store the password itself.</li>
        <li>For each payment in a statement you upload: the date, the shop name (cleaned from the bank's text), the amount and its category.</li>
        <li>Corrections you make to categories, so they can be applied again.</li>
      </ul>

      <h2 className={H2}>What we do not store</h2>
      <ul className={`${P} list-disc space-y-1 pl-5`}>
        <li>The uploaded file. It is read in memory and discarded.</li>
        <li>Your bank login, card numbers or account numbers.</li>
        <li>The bank's long description text, UPI references or running balances.</li>
        <li>Money received (salary, refunds): deposits are skipped when importing.</li>
      </ul>

      <h2 className={H2}>Why, and who sees it</h2>
      <p className={P}>
        Only to show you your own dashboard, charts and savings tips. Data is never sold, shared with advertisers, or
        used to train other models. There are no third-party analytics or ad trackers. The statement analysis runs on
        the service's own server, not on an outside AI service. Because the service is run by an individual, the person
        operating it can technically access the database, as with any small service. The data is held with the cloud
        providers used to run the site (the website, the application server and the database), over encrypted
        connections.
      </p>

      <h2 className={H2}>Your choices</h2>
      <ul className={`${P} list-disc space-y-1 pl-5`}>
        <li><strong>Download</strong> everything we hold about you as a file, from the Account page.</li>
        <li><strong>Delete</strong> your account and all of its data permanently, from the Account page. It cannot be undone.</li>
        <li>Your data stays until you delete it. Accounts are not removed automatically.</li>
      </ul>

      <h2 className={H2}>Security, honestly</h2>
      <p className={P}>
        Passwords are hashed, connections use HTTPS, sign-in attempts are rate limited and every account can only see
        its own data. But this is a small project: there is no email verification or password reset yet, and no
        guarantee that nothing can go wrong. Do not upload anything you are not comfortable trusting a small project
        with. If you prefer, you can run the project yourself from its source code.
      </p>

      <h2 className={H2}>The advice is not financial advice</h2>
      <p className={P}>
        Categories and tips are automatic estimates from your own transactions and can be wrong. Treat them as
        prompts to look closer, not as financial, tax or legal advice.
      </p>

      <h2 className={H2}>Contact</h2>
      <p className={P}>
        Questions or requests: open an issue at{" "}
        <a className="text-accent hover:underline" href="https://github.com/itsmepavithraa/spendsense/issues">
          github.com/itsmepavithraa/spendsense
        </a>
        . You can always delete your own data yourself without asking anyone.
      </p>
    </main>
  );
}
