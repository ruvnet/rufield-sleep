"use strict";
// Loaded only in the static Pages build. No network API or physical device events.
(() => {
  const key = "rufield-sleep.pages.v1",
    format = "rufield-sleep-diary/v1";
  const initial = (id, name) => ({
    id,
    name,
    bedtime: "22:30",
    minutes: 10,
    level: 2,
    nights: [],
  });
  let rows = [initial(1, "My room")],
    playback = null;
  const audioType = () => window.AudioContext || window.webkitAudioContext;
  const fail = (message) => {
    throw Error(message);
  };
  const check = (condition, message) => {
    if (!condition) fail(message);
  };
  const int = (n, min, max) => Number.isInteger(n) && n >= min && n <= max;
  const time = (t) =>
    typeof t === "string" && /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(t);
  function validDay(day) {
    if (typeof day !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(day))
      return false;
    const d = new Date(day + "T12:00:00Z");
    return Number.isFinite(+d) && d.toISOString().slice(0, 10) === day;
  }
  function checkedProfile(p) {
    check(
      p &&
        int(p.id, 1, 2147483647) &&
        typeof p.name === "string" &&
        p.name.trim().length > 0 &&
        p.name.length <= 50,
      "Invalid profile.",
    );
    check(
      time(p.bedtime) && int(p.minutes, 0, 30) && int(p.level, 1, 10),
      "Invalid routine.",
    );
    check(Array.isArray(p.nights), "Invalid night history.");
    const dates = new Set();
    const nights = p.nights.map((n) => {
      check(
        n &&
          validDay(n.date) &&
          time(n.bedtime) &&
          int(n.minutes, 0, 30) &&
          int(n.comfort, 1, 5) &&
          !dates.has(n.date),
        "Invalid diary entry.",
      );
      dates.add(n.date);
      return {
        date: n.date,
        bedtime: n.bedtime,
        minutes: n.minutes,
        comfort: n.comfort,
      };
    });
    return {
      id: p.id,
      name: p.name.trim(),
      bedtime: p.bedtime,
      minutes: p.minutes,
      level: p.level,
      nights,
    };
  }
  function parse(raw) {
    const data = JSON.parse(raw);
    check(
      data?.format === format &&
        Array.isArray(data.profiles) &&
        data.profiles.length > 0,
      "Choose a RuField Sleep diary file.",
    );
    const profiles = data.profiles.map(checkedProfile);
    check(
      profiles.some((p) => p.id === 1) &&
        new Set(profiles.map((p) => p.id)).size === profiles.length &&
        new Set(profiles.map((p) => p.name.toLowerCase())).size ===
          profiles.length,
      "Duplicate or missing profile.",
    );
    return profiles;
  }
  let storage,
    storageMessage = "";
  try {
    storage = window.sessionStorage;
    const saved = storage.getItem(key);
    if (saved) rows = parse(saved);
  } catch {
    storage = null;
    storageMessage =
      "Tab storage is unavailable. Download your diary before reloading.";
  }
  function save(next) {
    const raw = JSON.stringify({ format, profiles: next });
    if (storage) storage.setItem(key, raw);
    rows = next;
  }
  function median(values) {
    const sorted = [...values].sort((a, b) => a - b),
      mid = Math.floor(sorted.length / 2);
    return sorted.length % 2
      ? sorted[mid]
      : (sorted[mid - 1] + sorted[mid]) / 2;
  }
  // Match the local console's nearest-even rounding of half minutes.
  const nearest = (n) =>
    n % 1 === 0.5 ? Math.floor(n) + (Math.floor(n) % 2) : Math.round(n);
  function suggest(nights) {
    const recent = nights.slice(0, 14);
    if (recent.length < 3) return null;
    const minutes = (t) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3));
    const distance = (a, b) => Math.abs(((a - b + 2160) % 1440) - 720);
    const scores = recent.map((a) =>
      recent.reduce(
        (sum, b) => sum + distance(minutes(a.bedtime), minutes(b.bedtime)),
        0,
      ),
    );
    const best = recent[scores.indexOf(Math.min(...scores))].bedtime;
    const spread = median(
      recent.map((n) => distance(minutes(best), minutes(n.bedtime))),
    );
    if (spread > 90) return null;
    const liked = recent.filter((n) => n.comfort >= 4);
    return {
      bedtime: best,
      nights: recent.length,
      minutes:
        liked.length >= 3 ? nearest(median(liked.map((n) => n.minutes))) : null,
    };
  }
  function state(id) {
    const p = rows.find((p) => p.id === id);
    check(p, "Profile unavailable.");
    const nights = [...p.nights]
      .sort((a, b) => b.date.localeCompare(a.date))
      .slice(0, 30);
    return {
      profile: p,
      profiles: rows,
      nights,
      suggestion: suggest(nights),
      sensor: {
        mode: "Local console",
        enabled: false,
        history: [],
        count: 0,
        presence_at: null,
      },
      speaker: {
        connected: !!audioType(),
        remaining: playback
          ? Math.max(1, Math.ceil((playback.until - Date.now()) / 1000))
          : 0,
        message: playback
          ? "Pink noise playing"
          : audioType()
            ? "Play pink noise through this device. Keep the tab open during playback."
            : "Audio playback is unavailable in this browser.",
      },
    };
  }
  async function stop() {
    const session = playback;
    if (!session) return;
    playback = null;
    clearTimeout(session.timer);
    if (session.ctx.state !== "closed") await session.ctx.close();
  }
  async function play(p) {
    check(
      !playback && p.minutes > 0,
      "Choose a positive duration and stop the current session first.",
    );
    const Audio = audioType();
    check(Audio, "Audio playback is unavailable in this browser.");
    const ctx = new Audio(),
      session = { ctx, until: Date.now() + 60000 * p.minutes };
    playback = session;
    try {
      await ctx.resume();
      if (playback !== session) return;
      const src = ctx.createBufferSource(),
        gain = ctx.createGain(),
        now = ctx.currentTime,
        duration = p.minutes * 60;
      src.buffer = pinkBuffer(ctx, 4, 1, false);
      src.loop = true;
      src.connect(gain);
      gain.connect(ctx.destination);
      gain.gain.setValueAtTime(0, now);
      gain.gain.linearRampToValueAtTime(0.006 * p.level, now + 0.3);
      gain.gain.setValueAtTime(0.006 * p.level, now + duration - 0.3);
      gain.gain.linearRampToValueAtTime(0, now + duration);
      src.start(now);
      src.stop(now + duration);
      const finish = () => {
        if (playback === session) void stop();
      };
      src.onended = finish;
      session.timer = setTimeout(
        finish,
        Math.max(0, session.until - Date.now()),
      );
    } catch (error) {
      if (playback === session) await stop();
      throw error;
    }
  }
  async function call(action, body) {
    if (action === "stop") {
      await stop();
      return {};
    }
    const next = structuredClone(rows);
    if (action === "new") {
      const name = body.name.trim();
      check(
        name.length > 0 &&
          name.length <= 50 &&
          !next.some((p) => p.name.toLowerCase() === name.toLowerCase()),
        "Choose a unique profile name of 1 to 50 characters.",
      );
      const id = Math.max(...next.map((p) => p.id)) + 1;
      next.push(initial(id, name));
      save(next);
      return { profile: id };
    }
    const p = next.find((p) => p.id === body.profile);
    check(p, "Unknown profile.");
    switch (action) {
      case "start":
        await play(p);
        return {};
      case "routine":
        Object.assign(p, {
          bedtime: body.bedtime,
          minutes: body.minutes,
          level: body.level,
        });
        break;
      case "night":
        check(
          body.date <= document.querySelector("#nightForm [name=date]").max,
          "Choose today or an earlier evening.",
        );
        p.nights = p.nights.filter((n) => n.date !== body.date);
        p.nights.push({
          date: body.date,
          bedtime: body.bedtime,
          minutes: body.minutes,
          comfort: body.comfort,
        });
        break;
      case "forget":
        p.nights = [];
        break;
      default:
        fail("Use the local console for this device.");
    }
    checkedProfile(p);
    save(next);
    return { profile: p.id };
  }
  function download() {
    const blob = new Blob(
      [JSON.stringify({ format, profiles: rows }, null, 2)],
      { type: "application/json" },
    );
    const url = URL.createObjectURL(blob),
      a = document.createElement("a");
    a.href = url;
    a.download = "rufield-sleep-diary.json";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  window.addEventListener("pagehide", () => void stop());
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && playback && Date.now() >= playback.until)
      void stop();
  });
  window.ruFieldBrowser = {
    call,
    state,
    download,
    parse,
    restore: async (next) => {
      await stop();
      save(next);
    },
  };
  if (storageMessage)
    document.addEventListener("DOMContentLoaded", () => {
      document.getElementById("notice").textContent = storageMessage;
    });
})();
