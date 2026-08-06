#!/usr/bin/env node
'use strict';

/*
 * DOM-level smoke test for the POAFF web frontend.
 *
 * Loads the inline script of webserver/templates/index.html in a minimal
 * DOM sandbox, then simulates the "Start processing" click in several
 * scenarios and asserts the upload request is actually sent.
 *
 * This catches bugs like the ReferenceError that used to be thrown before
 * fetch('/upload') when the publish checkbox was unchecked.
 */

const fs = require('fs');
const vm = require('vm');

const htmlFile = process.argv[2] || 'webserver/templates/index.html';
const html = fs.readFileSync(htmlFile, 'utf8');
const match = html.match(/<script>([\s\S]*?)<\/script>/);
if (!match) {
  console.error('No inline <script> block found in ' + htmlFile);
  process.exit(1);
}
const script = match[1];

function makeEl(tagName) {
  return {
    tagName,
    value: '',
    checked: false,
    innerHTML: '',
    textContent: '',
    dataset: {},
    options: [],
    selectedIndex: -1,
    _listeners: {},
    classList: { add() {}, remove() {}, toggle() {} },
    style: {},
    appendChild() {},
    dispatchEvent() {},
    addEventListener(type, fn) { (this._listeners[type] ||= []).push(fn); },
    scrollIntoView() {},
    requestFullscreen() {},
    querySelector() { return makeEl('span'); },
  };
}

function buildSandbox() {
  const els = new Map();
  const calls = [];
  const globals = {
    console: { warn() {} },
    FormData: function () {
      this.data = {};
      this.append = (k, v) => { this.data[k] = v; };
      this.delete = (k) => { delete this.data[k]; };
    },
    fetch: async (url, opts) => {
      calls.push({ url, opts });
      if (url === '/current') {
        return { ok: true, status: 200, json: async () => ({ job_id: null }) };
      }
      if (url === '/upload') {
        return { ok: true, status: 200, json: async () => ({ job_id: 'test-job-123' }) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    },
    setInterval: () => 0,
    clearInterval: () => {},
    Date, Math, String, Number, JSON,
    window: { location: { href: '' }, addEventListener() {} },
    document: {
      getElementById: (id) => {
        if (!els.has(id)) els.set(id, makeEl('div'));
        return els.get(id);
      },
      createElement: (t) => makeEl(t),
      addEventListener() {},
      fullscreenElement: null,
    },
  };
  return { els, calls, globals };
}

function run(script, globals) {
  vm.createContext(globals);
  vm.runInContext(script, globals);
}

async function clickUpload(els) {
  const handler = els.get('upload-btn')._listeners['click'].slice(-1)[0];
  try {
    await handler();
    return null;
  } catch (err) {
    return err;
  }
}

(async () => {
  let failures = 0;
  const check = (cond, msg) => {
    console.log((cond ? 'PASS' : 'FAIL') + ': ' + msg);
    if (!cond) failures++;
  };

  // Scenario 1: default state (publish checkbox unchecked) - must reach /upload
  {
    const { els, calls, globals } = buildSandbox();
    run(script, globals);
    els.get('file-input')._file = { name: 'export_xml_bd_sia_2026-08-06-v04.zip' };
    const err = await clickUpload(els);
    check(err === null, 'scenario 1: no exception in click handler' + (err ? ' (' + err.message + ')' : ''));
    const up = calls.find((c) => c.url === '/upload');
    check(!!up, 'scenario 1: /upload request sent');
    if (up) {
      const fd = up.opts.body;
      check(fd.data.file.name === 'export_xml_bd_sia_2026-08-06-v04.zip', 'scenario 1: file attached to request');
      check(!('publish_release' in fd.data), 'scenario 1: publish_release absent when unchecked');
    }
  }

  // Scenario 2: publish checked + tag filled
  {
    const { els, calls, globals } = buildSandbox();
    run(script, globals);
    els.get('file-input')._file = { name: 'export_xml_bd_sia_2026-08-06-v04.zip' };
    els.get('publish-check').checked = true;
    globals.document.getElementById('gh-repo-upload').value = 'dprslt/poaff-as-a-service';
    globals.document.getElementById('gh-tag-upload').value = 'aip-08-26';
    globals.document.getElementById('gh-name-upload').value = 'AIP 08/26';
    const err = await clickUpload(els);
    check(err === null, 'scenario 2: no exception in click handler' + (err ? ' (' + err.message + ')' : ''));
    const up = calls.find((c) => c.url === '/upload');
    check(!!up, 'scenario 2: /upload request sent with publish checked');
    if (up) {
      const fd = up.opts.body;
      check(fd.data.publish_release === 'true', 'scenario 2: publish_release=true');
      check(fd.data.release_tag === 'aip-08-26', 'scenario 2: release_tag appended');
      check(fd.data.github_repo === 'dprslt/poaff-as-a-service', 'scenario 2: github_repo appended');
    }
  }

  // Scenario 3: publish checked but no tag -> publish_release must be dropped
  {
    const { els, calls, globals } = buildSandbox();
    run(script, globals);
    els.get('file-input')._file = { name: 'x.zip' };
    els.get('publish-check').checked = true;
    const err = await clickUpload(els);
    check(err === null, 'scenario 3: no exception in click handler' + (err ? ' (' + err.message + ')' : ''));
    const up = calls.find((c) => c.url === '/upload');
    check(!!up, 'scenario 3: /upload request sent');
    if (up) {
      check(!('publish_release' in up.opts.body.data), 'scenario 3: publish_release dropped without tag');
    }
  }

  if (failures > 0) {
    console.error(failures + ' check(s) failed');
    process.exit(1);
  }
  console.log('All smoke tests passed.');
})();
