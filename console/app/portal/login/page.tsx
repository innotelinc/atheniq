import Link from "next/link";

export const dynamic = "force-dynamic";

export const metadata = { title: "Student portal — AthenIQ Institute" };

export default async function PortalLoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;

  return (
    <div className="portal-auth">
      <h1 className="portal-title">Student portal</h1>
      <p className="portal-lede">
        Sign in with the same email and password you use in the AthenIQ app.
      </p>

      {error ? (
        <p className="portal-error" role="alert">
          That email and password do not match an account.
        </p>
      ) : null}

      {/* A real form post, so sign-in works with JavaScript off or before hydration. */}
      <form className="portal-form" action="/api/portal/login" method="post">
        <label>
          Email
          <input name="email" type="email" autoComplete="username" required />
        </label>
        <label>
          Password
          <input name="password" type="password" autoComplete="current-password" required />
        </label>
        <button className="btn" type="submit">
          Sign in
        </button>
      </form>

      <p className="portal-aside">
        Trouble signing in? Write to <a href="mailto:registrar@atheniq.institute">registrar@atheniq.institute</a>.
      </p>
      <p className="portal-aside">
        <Link href="/site">Back to the institute site</Link>
      </p>
    </div>
  );
}
