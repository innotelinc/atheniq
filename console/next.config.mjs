/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  serverExternalPackages: [],
  // The console is served on its own host (registrar.atheniq.institute) while
  // the public site answers on PUBLIC_SITE_HOSTS. Listing it keeps HMR and
  // server actions working when you browse through the real hostname in dev.
  allowedDevOrigins: ["registrar.atheniq.institute"],
};

export default nextConfig;
