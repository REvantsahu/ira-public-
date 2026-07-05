const makeWASocket = require("@whiskeysockets/baileys").default;
const { useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion, downloadMediaMessage } = require("@whiskeysockets/baileys");
const { Boom } = require("@hapi/boom");
const P = require("pino");
const qrcode = require("qrcode-terminal");
const fs = require("fs");
const path = require("path");
const http = require("http");

const PYTHON_BRIDGE = process.env.IRA_BRIDGE_URL || "http://127.0.0.1:8765";
const AUTH_DIR = path.join(__dirname, "auth");
const TMP_DIR = path.join(__dirname, "tmp");
fs.mkdirSync(TMP_DIR, { recursive: true });
fs.mkdirSync(AUTH_DIR, { recursive: true });

let sock = null;
let botJid = null;

async function postToPython(payload) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(payload);
    const opts = {
      hostname: new URL(PYTHON_BRIDGE).hostname,
      port: new URL(PYTHON_BRIDGE).port,
      path: "/incoming",
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Content-Length": Buffer.byteLength(data),
      },
      timeout: 300000, // 5 min timeout for slow agent responses
    };
    const req = http.request(opts, (res) => {
      let body = "";
      res.on("data", (chunk) => body += chunk);
      res.on("end", () => {
        try { resolve(JSON.parse(body)); } catch { resolve({ text: body }); }
      });
    });
    req.on("error", reject);
    req.on("timeout", () => { req.destroy(); reject(new Error("Python bridge timeout")); });
    req.write(data);
    req.end();
  });
}

function getTextFromMessage(m) {
  if (!m.message) return null;
  const msg = m.message;
  if (msg.conversation) return msg.conversation;
  if (msg.extendedTextMessage?.text) return msg.extendedTextMessage.text;
  if (msg.imageMessage?.caption) return msg.imageMessage.caption;
  if (msg.videoMessage?.caption) return msg.videoMessage.caption;
  if (msg.documentMessage?.caption) return msg.documentMessage.caption;
  return null;
}

function isVoiceMessage(m) {
  if (!m.message) return false;
  return !!m.message.audioMessage || !!m.message.pttMessage;
}

function isImageMessage(m) {
  return !!(m.message?.imageMessage);
}

async function downloadAndSave(m, mimeType) {
  try {
    const buffer = await downloadMediaMessage(m, "buffer", {});
    const ext = mimeType?.includes("audio") ? ".ogg" : mimeType?.includes("image") ? ".png" : ".bin";
    const filePath = path.join(TMP_DIR, `in_${Date.now()}_${Math.random().toString(36).slice(2)}${ext}`);
    fs.writeFileSync(filePath, buffer);
    return filePath;
  } catch (e) {
    console.error("Download failed:", e);
    return null;
  }
}

async function handleMessage(sock, m) {
  if (m.key.fromMe) return;
  if (!m.message) return;

  const jid = m.key.remoteJid;
  
  // Skip system broadcasts (status, groups with no messages, etc.)
  if (jid === "status@broadcast" || jid.endsWith("@g.us") || jid === "server@s.whatsapp.net") {
    return;
  }

  const sender = jid.split("@")[0];

  const text = getTextFromMessage(m);
  const isVoice = isVoiceMessage(m);
  const isImage = isImageMessage(m);

  const payload = { jid, sender, text: text || "" };

  if (isVoice) {
    const audioPath = await downloadAndSave(m, m.message.audioMessage?.mimetype || m.message.pttMessage?.mimetype || "audio/ogg");
    if (audioPath) {
      payload.audioPath = audioPath;
      payload.isVoice = true;
    }
  } else if (isImage) {
    const imagePath = await downloadAndSave(m, m.message.imageMessage?.mimetype || "image/png");
    if (imagePath) payload.imagePath = imagePath;
  }

  console.log(`\n📨 From ${sender}: ${isVoice ? "[voice note]" : isImage ? "[image]" : text?.slice(0, 80) || ""}`);

  try {
    const resp = await postToPython(payload);
    const { text: replyText, voiceNotePath, screenshotPath } = resp;

    if (replyText) {
      await sock.sendMessage(jid, { text: replyText });
      console.log(`✅ Sent text to ${sender}`);
    }
    if (voiceNotePath) {
      await sock.sendMessage(jid, { audio: { url: voiceNotePath }, mimetype: "audio/ogg; codecs=opus", ptt: true });
      console.log(`🎤 Sent voice note to ${sender}`);
    }
    if (screenshotPath) {
      await sock.sendMessage(jid, { image: { url: screenshotPath }, caption: "Screen capture" });
      console.log(`📸 Sent screenshot to ${sender}`);
    }
  } catch (e) {
    console.error("Python bridge error:", e);
    await sock.sendMessage(jid, { text: "⚠️ IRA bridge error: " + e.message });
  }
}

async function startSock() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { version } = await fetchLatestBaileysVersion();
  sock = makeWASocket({
    version,
    auth: state,
    logger: P({ level: "warn" }),
    browser: ["IRA-Bridge", "Ubuntu", "1.0"],
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", (u) => {
    const { connection, lastDisconnect, qr } = u;
    if (qr) {
      console.log("\n📱 Scan this QR with WhatsApp → Linked Devices\n");
      qrcode.generate(qr, { small: true });
    }
    if (connection === "close") {
      const code = new Boom(lastDisconnect?.error)?.output?.statusCode;
      if (code !== DisconnectReason.loggedOut) {
        console.log("Reconnecting...");
        setTimeout(startSock, 3000);
      } else {
        console.log("Logged out. Delete whatsapp/auth to re-link.");
      }
    }
    if (connection === "open") {
      console.log("✅ IRA connected to WhatsApp");
      botJid = sock.user?.id;
    }
  });

  sock.ev.on("messages.upsert", async ({ messages }) => {
    for (const m of messages) {
      try {
        await handleMessage(sock, m);
      } catch (e) {
        console.error("handle error:", e);
      }
    }
  });

  return sock;
}

console.log("🚀 Starting IRA WhatsApp bridge...");
startSock().catch(console.error);