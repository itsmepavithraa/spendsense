/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // Standard browser protections, sent with every page.
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" }, // don't guess file types
          { key: "X-Frame-Options", value: "DENY" }, // the site can't be framed by another site (clickjacking)
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" }, // the app never needs these
          { key: "Strict-Transport-Security", value: "max-age=31536000" },
        ],
      },
    ];
  },
};

export default nextConfig;
