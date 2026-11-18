"use strict";
const hosted = window.ruFieldBrowser;
const el = (id) => document.getElementById(id);
let active = 1,
  snapshot,
  version = 0,
  previewContext,
  previewGeneration = 0;
const message = (text) => {
  el("notice").textContent = text;
};
function showTab(id) {
  document.querySelectorAll(".pane").forEach((p) => (p.hidden = p.id !== id));
  document
    .querySelectorAll(".tabs button")
    .forEach((b) => b.setAttribute("aria-pressed", b.dataset.tab === id));
}
document
  .querySelectorAll("[data-tab]")
  .forEach((b) => (b.onclick = () => showTab(b.dataset.tab)));
function trace(canvas, values, color) {
  const c = canvas.getContext("2d"),
    w = canvas.width,
    h = canvas.height;
  c.clearRect(0, 0, w, h);
  c.strokeStyle = "#343b52";
  c.lineWidth = 1;
  for (let y = 16; y < h; y += 24) {
    c.beginPath();
    c.moveTo(0, y);
    c.lineTo(w, y);
    c.stroke();
  }
  if (!values.length) return;
  const max = Math.max(1, ...values);
  c.strokeStyle = color;
  c.lineWidth = 3;
  c.beginPath();
  values.forEach((v, i) => {
    const x = 2 + (i * (w - 4)) / Math.max(1, values.length - 1),
      y = h - 6 - ((h - 12) * v) / max;
    i ? c.lineTo(x, y) : c.moveTo(x, y);
  });
  c.stroke();
}
function artwork() {
  const c = el("wave").getContext("2d");
  for (let j = 0; j < 12; j++) {
    c.beginPath();
    c.lineWidth = 1.3;
    c.strokeStyle =
      "hsla(" + (250 - j * 2) + ",60%,78%," + (0.2 + j * 0.045) + ")";
    for (let x = 0; x < 480; x += 2) {
      const env = Math.sin((Math.PI * x) / 480) ** 1.7,
        y =
          76 +
          env *
            (Math.sin(x / 44 + j * 0.19) * 28 +
              Math.sin(x / 23 + j * 0.31) * 18) +
          j * 1.6;
      x ? c.lineTo(x, y) : c.moveTo(x, y);
    }
    c.stroke();
  }
}
async function call(action, body) {
  if (hosted) return hosted.call(action, body);
  const res = await fetch("/api/" + action, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-RuField-Console": "1" },
    body: JSON.stringify(body),
  });
  const result = await res.json();
  if (!res.ok) throw Error(result.error);
  return result;
}
async function refresh(forms = false) {
  const requested = ++version,
    id = active;
  let s;
  if (hosted) {
    s = hosted.state(id);
  } else {
    const response = await fetch("/api/state?profile=" + id, {
      cache: "no-store",
    });
    s = await response.json();
    if (!response.ok) throw Error(s.error);
  }
  if (requested !== version || id !== active) return;
  snapshot = s;
  const p = s.profile,
    f = s.sensor,
    output = s.speaker;
  if (forms) {
    el("profiles").replaceChildren(
      ...s.profiles.map((x) => new Option(x.name, x.id)),
    );
    el("profiles").value = String(active);
    for (const key of ["bedtime", "minutes", "level"])
      el("routineForm").elements[key].value = p[key];
    el("nightForm").elements.bedtime.value = p.bedtime;
    el("nightForm").elements.minutes.value = p.minutes;
  }
  el("who").textContent = p.name;
  el("bed").textContent = p.bedtime;
  el("timer").textContent = p.minutes + " min";
  el("gain").textContent = p.level + " / 10";
  el("mode").textContent = f.mode;
  el("mode").className = "pill" + (f.mode === "Live" ? " live" : "");
  el("fieldInfo").textContent = f.history.length
    ? f.count +
      " events in the latest frame · " +
      f.mode.toLowerCase() +
      " feed"
    : f.enabled
      ? "Waiting for RuField on the configured viewer port."
      : "Connect a local RuField viewer to see room activity.";
  if (hosted)
    el("fieldInfo").textContent =
      "Manage your RuField feed and bed exit detection in the local hardware console.";
  el("usePresence").disabled = !f.presence_at;
  el("sensorBtn").textContent = f.enabled ? "Disconnect feed" : "Connect feed";
  trace(el("signal"), f.history, "#88d6c3");
  el("speakerInfo").textContent =
    output.message +
    (output.remaining ? " · " + output.remaining + " s remaining" : "");
  el("usb").textContent = output.connected ? "Disconnect USB" : "Connect USB";
  el("play").disabled = !output.connected || output.remaining > 0 || !p.minutes;
  el("stop").disabled = hosted ? !output.remaining : !output.connected;
  const rec = s.suggestion;
  el("adopt").hidden = !rec;
  el("suggestion").textContent = rec
    ? "Around " +
      rec.bedtime +
      " across " +
      rec.nights +
      " logged evenings. " +
      (rec.minutes === null
        ? "Keep logging sound comfort to personalize duration."
        : rec.minutes + " minutes of sound on evenings you rated comfortable.")
    : s.nights.length < 3
      ? "Log " +
        (3 - s.nights.length) +
        " more evening" +
        (s.nights.length === 2 ? "" : "s") +
        " to estimate your usual bedtime."
      : "Your bedtimes vary. Keep your preferred time for now.";
  historyTable(s.nights);
}
function historyTable(rows) {
  const holder = el("history");
  holder.replaceChildren();
  if (!rows.length) {
    holder.textContent = "Your logged evenings will appear here.";
    return;
  }
  const table = document.createElement("table");
  [
    ["Evening", "Bedtime", "Minutes", "Comfort"],
    ...rows.map((n) => [n.date, n.bedtime, n.minutes, n.comfort + "/5"]),
  ].forEach((cells, i) => {
    const row = table.insertRow();
    cells.forEach((v) => {
      const cell = document.createElement(i ? "td" : "th");
      cell.textContent = v;
      row.append(cell);
    });
  });
  holder.append(table);
}
function handle(fn) {
  return async (event) => {
    event?.preventDefault();
    try {
      await fn(event);
    } catch (e) {
      message(e.message);
    }
  };
}
async function act(name, body, notice, forms = false) {
  await call(name, body);
  await refresh(forms);
  message(notice);
}
el("profiles").onchange = handle(async () => {
  active = Number(el("profiles").value);
  await refresh(true);
  message("");
});
el("routineForm").onsubmit = handle(async (e) => {
  const f = e.target.elements;
  await act(
    "routine",
    {
      profile: active,
      bedtime: f.bedtime.value,
      minutes: +f.minutes.value,
      level: +f.level.value,
    },
    "Routine saved.",
    true,
  );
});
el("nightForm").onsubmit = handle(async (e) => {
  const f = e.target.elements;
  await act(
    "night",
    {
      profile: active,
      date: f.date.value,
      bedtime: f.bedtime.value,
      minutes: +f.minutes.value,
      comfort: +f.comfort.value,
    },
    "Evening saved.",
  );
});
el("newForm").onsubmit = handle(async (e) => {
  const f = e.target;
  const result = await call("new", { name: f.elements.name.value });
  active = result.profile;
  await refresh(true);
  f.reset();
  message("Profile created.");
});
el("forget").onclick = handle(async () => {
  if (confirm("Erase all logged evenings for " + snapshot.profile.name + "?"))
    await act("forget", { profile: active }, "Diary erased.");
});
el("sensorBtn").onclick = handle(() =>
  act(
    "sensor",
    { enabled: !snapshot.sensor.enabled },
    "Sensor connection updated.",
  ),
);
el("usb").onclick = handle(() =>
  act(
    snapshot.speaker.connected ? "disconnect" : "connect",
    {},
    "Speaker connection updated.",
  ),
);
el("play").onclick = handle(() =>
  act(
    "start",
    { profile: active, guard: el("guard").checked },
    "Wind down started.",
  ),
);
el("stop").onclick = handle(() => act("stop", {}, "Stop requested."));
el("adopt").onclick = handle(async () => {
  const r = snapshot.suggestion,
    p = snapshot.profile;
  await act(
    "routine",
    {
      profile: active,
      bedtime: r.bedtime,
      minutes: r.minutes ?? p.minutes,
      level: p.level,
    },
    "Personalized routine saved.",
    true,
  );
});
el("preview").onclick = handle(async () => {
  const gen = ++previewGeneration;
  if (previewContext) {
    await previewContext.close();
    previewContext = null;
    el("preview").textContent = "Hear a sample";
    return;
  }
  const Audio = window.AudioContext || window.webkitAudioContext;
  if (!Audio) throw Error("Audio playback is unavailable in this browser.");
  const ctx = new Audio();
  previewContext = ctx;
  await ctx.resume();
  const buf = pinkBuffer(ctx, 3, 0.04, true);
  const src = ctx.createBufferSource();
  src.buffer = buf;
  src.connect(ctx.destination);
  el("preview").textContent = "Stop sample";
  src.onended = () => {
    if (gen === previewGeneration) {
      ctx.close();
      previewContext = null;
      el("preview").textContent = "Hear a sample";
    }
  };
  src.start();
});
const today = new Date();
const localDate = [
  today.getFullYear(),
  String(today.getMonth() + 1).padStart(2, "0"),
  String(today.getDate()).padStart(2, "0"),
].join("-");
el("nightForm").elements.date.value = localDate;
el("nightForm").elements.date.max = localDate;
artwork();
refresh(true).catch((e) => message(e.message));
setInterval(() => refresh().catch((e) => message(e.message)), 2500);

el("usePresence").onclick = handle(async () => {
  await refresh();
  const when = snapshot.sensor.presence_at;
  if (!when) {
    message("Waiting for a recent live presence observation.");
    return;
  }
  const time = new Date(when * 1000),
    pad = (n) => String(n).padStart(2, "0"),
    form = el("nightForm").elements;
  form.date.value = [
    time.getFullYear(),
    pad(time.getMonth() + 1),
    pad(time.getDate()),
  ].join("-");
  form.bedtime.value = pad(time.getHours()) + ":" + pad(time.getMinutes());
  message(
    "Review the observed room time, then save if it matches your bedtime.",
  );
});

function pinkBuffer(ctx, seconds, amplitude, fade) {
  const buffer = ctx.createBuffer(
    1,
    Math.round(seconds * ctx.sampleRate),
    ctx.sampleRate,
  );
  const samples = buffer.getChannelData(0);
  let b0 = 0,
    b1 = 0,
    b2 = 0;
  for (let i = 0; i < samples.length; i++) {
    const w = Math.random() * 2 - 1;
    b0 = 0.99765 * b0 + 0.099046 * w;
    b1 = 0.963 * b1 + 0.2965164 * w;
    b2 = 0.57 * b2 + 1.0526913 * w;
    const envelope = fade
      ? Math.min(1, i / 2500, (samples.length - i) / 5000)
      : 1;
    samples[i] =
      Math.max(-1, Math.min(1, (b0 + b1 + b2 + 0.1848 * w) * 0.15)) *
      amplitude *
      envelope;
  }
  return buffer;
}
if (hosted) {
  el("edition").textContent = "BROWSER CONSOLE";
  el("footerEdition").textContent = "Browser edition";
  el("hostingNote").hidden = el("diaryFiles").hidden = false;
  el("outputTitle").textContent = "This device";
  for (const id of ["sensorBtn", "usePresence", "presenceHelp", "usb"])
    el(id).hidden = true;
  el("guard").closest("label").hidden = true;
  el("guard").checked = false;
  el("exportDiary").onclick = handle(() => hosted.download());
  el("importDiary").onclick = () => el("diaryFile").click();
  el("diaryFile").onchange = handle(async () => {
    const input = el("diaryFile"),
      file = input.files[0];
    input.value = "";
    if (!file) return;
    if (file.size > 4 * 1024 * 1024)
      throw Error("Choose a diary file smaller than 4 MB.");
    const restored = hosted.parse(await file.text());
    if (
      !confirm(
        "Replace the profiles and diary entries in this tab with the downloaded copy?",
      )
    )
      return;
    await hosted.restore(restored);
    active = 1;
    await refresh(true);
    message("Diary restored in this tab.");
  });
}
