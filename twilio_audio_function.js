const https = require("https");

exports.handler = function(context, event, callback) {
  var text = event.text || "Namaste";
  var lang = event.lang || "hi-IN";
  var key = context.SARVAM_KEY || "";
  if (!key) { console.log("NO SARVAM_KEY"); return callback("No key"); }
  console.log("TTS:", text.substring(0, 60), "lang:", lang);
  var body = JSON.stringify({
    inputs: [text.substring(0, 500)],
    target_language_code: lang,
    speaker: "anushka",
    model: "bulbul:v2",
    pitch: 0, pace: 1.0, loudness: 1.5,
    enable_preprocessing: true
  });
  var rq = https.request({
    hostname: "api.sarvam.ai", path: "/text-to-speech", method: "POST",
    headers: { "api-subscription-key": key, "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body) }
  }, function(rs) {
    var d = ""; rs.on("data", function(c) { d += c; }); rs.on("end", function() {
      try {
        var audio = JSON.parse(d).audios[0];
        var buf = Buffer.from(audio, "base64");
        console.log("Audio OK:", buf.length, "bytes");
        var resp = new Twilio.Response();
        resp.appendHeader("Content-Type", "audio/wav");
        resp.appendHeader("Cache-Control", "public, max-age=300");
        resp.setBody(buf);
        return callback(null, resp);
      } catch(e) {
        console.log("TTS err:", e.message, d.substring(0, 100));
        return callback("TTS failed");
      }
    });
  });
  rq.on("error", function(e) { console.log("Net err:", e.message); callback("Net error"); });
  rq.setTimeout(8000, function() { rq.destroy(); callback("Timeout"); });
  rq.write(body); rq.end();
};
