// Audit only the locally built static shell; no production or authenticated data.
module.exports = {
  ci: {
    collect: {
      staticDistDir: './web/dist',
      url: ['http://localhost/'],
      isSinglePageApplication: true,
      numberOfRuns: 1,
    },
    assert: {
      assertions: {
        'categories:accessibility': ['error', { minScore: 0.9 }],
        'categories:performance': ['warn', { minScore: 0.8 }],
        'categories:seo': ['warn', { minScore: 0.9 }],
      },
    },
    upload: { target: 'filesystem', outputDir: './artifacts/lighthouse' },
  },
};
