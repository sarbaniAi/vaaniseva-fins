const https = require("https");

function callApp(from, msg) {
  return new Promise(function(ok) {
    var token = (process.env.T1 || "") + (process.env.T2 || "") + (process.env.T3 || "") + (process.env.T4 || "");
    var body = JSON.stringify({from: from, message: msg});
    console.log("Calling Databricks App, token len:", token.length);
    var rq = https.request({
      hostname: "yatra-voice-agent-984752964297111.11.azure.databricksapps.com",
      path: "/api/whatsapp/process", method: "POST",
      headers: {"Authorization": "Bearer " + token, "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body)}
    }, function(rs) {
      var d = ""; rs.on("data", function(c) { d += c; }); rs.on("end", function() {
        console.log("App resp:", d.substring(0, 150));
        try { ok(JSON.parse(d).reply || "Error. Reply *menu*"); }
        catch(e) { ok("App error: " + d.substring(0, 100) + " Reply *menu*"); }
      });
    });
    rq.on("error", function(e) { console.log("Net err:", e.message); ok("Connection error. Reply *menu*"); });
    rq.setTimeout(9000, function() { rq.destroy(); ok("Timeout. Reply *menu*"); });
    rq.write(body); rq.end();
  });
}

exports.handler = async function(context, event, callback) {
  var body = (event.Body || "").trim();
  var from = event.From || "";
  console.log("IN:", from, body);
  var reply = await callApp(from, body);
  console.log("OUT:", reply.substring(0, 80));
  var twiml = new Twilio.twiml.MessagingResponse();
  twiml.message(reply);
  return callback(null, twiml);
};
