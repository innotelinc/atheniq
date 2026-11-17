/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  serverExternalPackages: [],
  // The console is served on its own host — registrar.atheniq.institute — and
  // the public site is a separate static deployment, so this is the only origin
  // that needs listing: it keeps HMR and server actions working when you browse
  // through the real hostname in dev.
  allowedDevOrigins: ["registrar.atheniq.institute"],
};

export default nextConfig;
