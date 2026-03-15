import adapter from '@sveltejs/adapter-static';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  kit: {
    adapter: adapter({
      pages: '../../interface/dist',
      assets: '../../interface/dist',
      fallback: 'index.html',
      precompress: false,
      strict: false,
    }),
    paths: {
      base: '',
    },
  },
};

export default config;
