import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {qrMatrix,qrPath,capacity,QUIET} from '../qr.mjs';

// Fingerprints of symbols made by an independent QR library (python-qrcode 8.2, level L, forced byte
// mode, no border) with the same mask. Matching them square for square means a phone reads ours.
const KNOWN=[
  ['HELLO',0,1,'d51e6b3d78d8b096ca2040e60a6b738e6d61f498c4cb0c3b63f035650114d050'],
  ['https://parlu-relay.vercel.app/invite#'+'x'.repeat(120),5,8,'82588cc5dceb290caf9843881e2b8fb907601f546b43640d4eeabab792f407ea'],
  ['https://parlu-relay.vercel.app/invite#'+'Ab9_-'.repeat(80),2,14,'f7b1cbd659431b958a093f7505f46ded3093f6bca438443e070268d940c88f5e'],
  ['Héllo, “Parlu” ✓ £5',3,2,'2ba2cfe5b70d63e2992b5e34685511fb55a5663f0ea90bc42fb312a6bf5c5ed5'],
];
const print=matrix=>createHash('sha256').update(matrix.modules.map(row=>row.map(v=>v?'1':'0').join('')).join('\n')).digest('hex');

test('symbols match an independent encoder square for square',()=>{
  for(const [text,mask,version,expected] of KNOWN){
    const matrix=qrMatrix(text,{mask});
    assert.equal(matrix.version,version,text.slice(0,20));
    assert.equal(matrix.size,version*4+17);
    assert.equal(print(matrix),expected,text.slice(0,20));
  }
});

test('the least crowded mask is chosen and the size grows with the text',()=>{
  const short=qrMatrix('HELLO'),long=qrMatrix('https://parlu-relay.vercel.app/invite#'+'Ab9_-'.repeat(80));
  assert.ok(short.mask>=0&&short.mask<=7);
  assert.equal(short.version,1);assert.equal(long.version,14);
  assert.equal(capacity(1),17);assert.equal(capacity(10),271);assert.equal(capacity(40),2953);
  assert.throws(()=>qrMatrix('x'.repeat(2954)),/Too long/);
});

test('the drawing keeps four quiet squares round the code',()=>{
  const drawn=qrPath(qrMatrix('HELLO',{mask:0}));
  assert.equal(drawn.size,21+QUIET*2);
  // The top-left finder starts at the quiet edge, with a full seven-square top row.
  assert.ok(drawn.path.startsWith(`M${QUIET},${QUIET}h7v1h-7z`));
  assert.doesNotMatch(drawn.path,/[^MhvzH0-9,\-]/);
});
