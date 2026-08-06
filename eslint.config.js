'use strict';

const browserGlobals = [
  'document', 'window', 'console', 'fetch', 'FormData',
  'setInterval', 'clearInterval', 'setTimeout', 'clearTimeout',
  'Date', 'Math', 'String', 'Number', 'JSON', 'Event',
  'Blob', 'FileReader', 'navigator',
];

module.exports = [
  {
    files: ['build/**/*.js'],
    languageOptions: {
      ecmaVersion: 2020,
      sourceType: 'script',
      globals: Object.fromEntries(browserGlobals.map((g) => [g, 'readonly'])),
    },
    rules: {
      'no-undef': 'error',
      'no-redeclare': 'error',
      'no-const-assign': 'error',
      'no-unused-vars': ['error', { vars: 'local', args: 'none' }],
    },
  },
];
