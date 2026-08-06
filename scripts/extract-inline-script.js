#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');

const [srcHtml, outJs] = process.argv.slice(2);
if (!srcHtml || !outJs) {
  console.error('Usage: node scripts/extract-inline-script.js <index.html> <out.js>');
  process.exit(1);
}

const html = fs.readFileSync(srcHtml, 'utf8');
const match = html.match(/<script>([\s\S]*?)<\/script>/);
if (!match) {
  console.error('No inline <script> block found in ' + srcHtml);
  process.exit(1);
}

const wrapper = '(function () {\n' + match[1] + '\n})();\n';
fs.mkdirSync(path.dirname(outJs), { recursive: true });
fs.writeFileSync(outJs, wrapper);
console.log('Extracted inline script (' + match[1].length + ' bytes) -> ' + outJs);
