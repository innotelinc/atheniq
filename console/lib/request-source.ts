/**
 * Where a sign-in attempt came from, for the security log.
 *
 * Behind a proxy the first x-forwarded-for hop is the client; otherwise the
 * platform's x-real-ip. Without either header the request reached the server
 * directly, and the Host decides whether that was this machine or a LAN client.
 */
export function requestSource(request: Request): string {
  const forwarded = request.headers.get("x-forwarded-for");
  const real = request.headers.get("x-real-ip");
  const ip = (forwarded ? forwarded.split(",")[0] : real || "").trim();
  const host = request.headers.get("host") || "";
  const loopbackHost = /^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/i.test(host);

  if (!ip) return loopbackHost ? "this computer" : "direct connection";
  if (ip === "::1" || ip === "127.0.0.1" || ip === "::ffff:127.0.0.1") return "this computer";
  return ip.slice(0, 45);
}
