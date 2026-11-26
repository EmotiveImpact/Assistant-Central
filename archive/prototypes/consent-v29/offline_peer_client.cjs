'use strict';
// Fixed dependency-free offline client. No owner tools, network or dynamic code.
// stdin: trusted explicit steps; stdout: protocol only. Extra fds: replies/reports.
const fs = require('node:fs');
const decoder = new TextDecoder('utf-8', {fatal: true});
const pending = new Map();
const VERSION = '2025-06-18';
function read(fd, limit) {
  let bytes = pending.get(fd) || Buffer.alloc(0);
  for (;;) {
    const newline = bytes.indexOf(10);
    if (newline >= 0) {
      if (newline > limit) throw Error('Oversize frame');
      pending.set(fd, bytes.subarray(newline + 1));
      return JSON.parse(decoder.decode(bytes.subarray(0, newline)));
    }
    if (bytes.length > limit) throw Error('Oversize frame');
    const chunk = Buffer.alloc(Math.min(4096, limit + 1 - bytes.length));
    const count = fs.readSync(fd, chunk, 0, chunk.length, null);
    if (!count) throw Error('Incomplete frame');
    bytes = Buffer.concat([bytes, chunk.subarray(0, count)]);
  }
}
function emit(fd, value, limit) {
  const raw = Buffer.from(JSON.stringify(value), 'utf8');
  if (raw.length > limit) throw Error('Oversize frame');
  const frame = Buffer.concat([raw, Buffer.from('\n')]);
  let offset = 0;
  while (offset < frame.length) {
    const count = fs.writeSync(fd, frame, offset, frame.length - offset);
    if (count <= 0) throw Error('No output progress');
    offset += count;
  }
}
function object(value) { return value !== null && typeof value === 'object' && !Array.isArray(value); }
function main() {
  if (process.argv.length !== 4) throw Error('Invalid descriptors');
  const fds = process.argv.slice(2).map(value => {
    if (!/^[0-9]+$/.test(value) || !Number.isSafeInteger(Number(value)) || Number(value) < 3)
      throw Error('Invalid descriptor');
    return Number(value);
  });
  const [replies, reports] = fds;
  if (replies === reports) throw Error('Invalid descriptors');
  const config = read(0, 65535);
  if (!object(config) || Object.keys(config).sort().join(',') !== 'envelope,proposal_id' ||
      !object(config.envelope) || typeof config.proposal_id !== 'string' ||
      [...config.proposal_id].length < 1 || [...config.proposal_id].length > 64)
    throw Error('Invalid inert configuration');
  let seq = 0;
  let initialized = false;
  function rpc(method, params, notification = false) {
    ++seq;
    const message = {jsonrpc: '2.0', method};
    if (!notification) message.id = seq;
    if (params !== undefined) message.params = params;
    emit(1, message, 16384);
    if (notification) return;
    const response = read(replies, 32768);
    if (!object(response) || response.jsonrpc !== '2.0' || response.id !== seq ||
        ('result' in response) === ('error' in response)) throw Error('Unexpected response');
    return response;
  }
  for (;;) {
    const command = read(0, 65535);
    if (!object(command) || Object.keys(command).join(',') !== 'step') throw Error('Invalid step');
    let response;
    if (command.step === 'discover') {
      if (!initialized) {
        response = rpc('initialize', {protocolVersion: VERSION, capabilities: {},
          clientInfo: {name: 'fictional-node-peer', version: '1'}});
        if ('error' in response || !object(response.result) || response.result.protocolVersion !== VERSION)
          throw Error('Incompatible handshake');
        rpc('notifications/initialized', undefined, true);
        initialized = true;
      }
      response = rpc('tools/list');
    } else if (command.step === 'propose') {
      response = rpc('tools/call', {name: 'propose', arguments: config});
    } else if (command.step === 'status') {
      response = rpc('tools/call', {name: 'proposal_status', arguments: {proposal_id: config.proposal_id}});
    } else if (command.step === 'inbox') {
      response = rpc('tools/call', {name: 'inbox', arguments: {}});
    } else throw Error('Unknown fixed step');
    emit(reports, {pid: process.pid, response}, 65535);
  }
}
try { main(); } catch (_) { process.exitCode = 1; }
