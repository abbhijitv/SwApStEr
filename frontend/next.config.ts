import type {NextConfig} from 'next';
const config: NextConfig = {
  async headers() {
    return ['/auth/:path*', '/signup', '/login', '/forgot-password', '/reset-password', '/account'].map(source => ({source, headers: [{key: 'Referrer-Policy', value: 'no-referrer'}]}));
  },
};
export default config;
