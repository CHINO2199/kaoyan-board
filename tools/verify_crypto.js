/* 跨端一致性验证：用与前端完全相同的逻辑解密 Python 生成的 data.enc
 * 用法：node tools/verify_crypto.js [主密码]
 * 依赖：npm i crypto-js
 */
const fs = require('fs');
const path = require('path');
const CryptoJS = require('crypto-js');

const PWD = process.argv[2] || process.env.KAOYAN_KEY || 'YOUR_MASTER_PASSWORD_HERE';
const PAD_BYTE = 0x20;

function u8ToWA(u8) {
  const w = [];
  for (let i = 0; i < u8.length; i++) w[i >>> 2] = (w[i >>> 2] || 0) | (u8[i] << (24 - (i % 4) * 8));
  return CryptoJS.lib.WordArray.create(w, u8.length);
}
function waToU8(wa) {
  const u8 = new Uint8Array(wa.sigBytes);
  for (let i = 0; i < wa.sigBytes; i++) u8[i] = (wa.words[i >>> 2] >>> (24 - (i % 4) * 8)) & 0xff;
  return u8;
}
function deriveKey(pwd) {
  const src = waToU8(CryptoJS.enc.Utf8.parse(pwd));
  const key = new Uint8Array(32).fill(PAD_BYTE);
  for (let i = 0; i < Math.min(32, src.length); i++) key[i] = src[i];
  return u8ToWA(key);
}
function aesDecrypt(b64, pwd) {
  const all = waToU8(CryptoJS.enc.Base64.parse(String(b64).replace(/\s+/g, '')));
  if (all.length <= 16) throw new Error('数据格式不正确');
  const dec = CryptoJS.AES.decrypt(
    { ciphertext: u8ToWA(all.slice(16)) },
    deriveKey(pwd),
    { iv: u8ToWA(all.slice(0, 16)), mode: CryptoJS.mode.CBC, padding: CryptoJS.pad.Pkcs7 }
  );
  const txt = dec.toString(CryptoJS.enc.Utf8);
  if (!txt) throw new Error('密码不正确');
  return txt;
}

const ENC_PATH = path.resolve(__dirname, '..', 'data.enc');
if (!fs.existsSync(ENC_PATH)) { console.log('× 找不到 data.enc，请先运行 python update.py'); process.exit(1); }
const enc = fs.readFileSync(ENC_PATH, 'utf8').trim();
console.log('使用主密码：' + (PWD === 'YOUR_MASTER_PASSWORD_HERE' ? '(默认占位符)' : '******'));

// 1) 正确密码
try {
  const obj = JSON.parse(aesDecrypt(enc, PWD));
  console.log('✓ 正确密码解密成功');
  console.log('  milestones:', obj.milestones.length, '| daily_logs:', obj.daily_logs.length, '| notes:', obj.notes.length);
  console.log('  笔记正文长度:', obj.notes[0].content.length, '字符');
  console.log('  notes[0].title =', obj.notes[0].title, '| uploaded_at =', obj.notes[0].uploaded_at);
} catch (e) {
  console.log('× 正确密码解密失败:', e.message);
  process.exit(1);
}

// 2) 错误密码必须失败
let bad = false;
try {
  const t = aesDecrypt(enc, 'wrong-password');
  bad = !t;
  if (t) { console.log('× 错误密码竟然解密成功，存在安全缺陷'); process.exit(1); }
} catch (e) {
  bad = true;
}
console.log(bad ? '✓ 错误密码被正确拒绝' : '× 错误密码未被拒绝');
