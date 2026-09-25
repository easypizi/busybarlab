var CARLOS_RULES = (function () {
  var CYCLE_START = "2026-09-21";
  var FIRST_OPEN = "2026-09-22";
  var CYCLE_END = "2027-03-07";
  var RACE_TEXT = "Гонка 5 или 10 км вместо этой сессии.";
  var VOLUME_TEXT = "Объём минус 40%.";
  var EARLY_TEXT = "Старт 22 сентября.";
  var LATE_TEXT = "Цикл кончился. Новый план собираем отдельно.";
  var STATUS = { done: "сделано", partial: "частично", skipped: "пропуск" };

  function parseISO(iso) {
    var parts = String(iso || "").split("-");
    return new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
  }

  function fmt(date) {
    var month = date.getMonth() + 1;
    var day = date.getDate();
    return (
      date.getFullYear() +
      "-" +
      (month < 10 ? "0" : "") +
      month +
      "-" +
      (day < 10 ? "0" : "") +
      day
    );
  }

  function todayISO(date) {
    return fmt(date || new Date());
  }

  function addDays(iso, count) {
    var date = parseISO(iso);
    date.setDate(date.getDate() + count);
    return fmt(date);
  }

  function mondayOf(iso) {
    var date = parseISO(iso);
    var day = date.getDay();
    var delta = day === 0 ? -6 : 1 - day;
    return addDays(iso, delta);
  }

  function screenFor(today) {
    if (today < FIRST_OPEN) return "early";
    if (today > CYCLE_END) return "late";
    return "card";
  }

  function shiftCursor(cursor, delta) {
    var next = addDays(cursor, delta);
    if (next < CYCLE_START || next > CYCLE_END) return cursor;
    return next;
  }

  function choiceOptions(day) {
    return (day && day.choice && day.choice.options) || [];
  }

  function needsChoice(day, state) {
    return !!(day && day.choice && day.choice.required && !state["friday:" + day.date]);
  }

  function chosenOption(day, state) {
    var id = state["friday:" + day.date];
    var options = choiceOptions(day);
    var i;
    for (i = 0; i < options.length; i += 1) {
      if (options[i].id === id) return options[i];
    }
    return null;
  }

  function raceKey(day) {
    return "raceWeek:" + mondayOf(day.date);
  }

  function raceSide(day, state) {
    return (state && state[raceKey(day)]) || "";
  }

  function isStart(day, side) {
    return !!(side && day.weekday === side);
  }

  function hidesExercises(day, side) {
    if (!side) return false;
    if (day.weekday === side) return true;
    if (side === "wed" && day.sessionId === "run-intervals") return true;
    return false;
  }

  function volumeNote(day, side) {
    if (!side || day.deload || day.weekday === "sun" || day.weekday === side) return "";
    return VOLUME_TEXT;
  }

  function exerciseNames(day, state) {
    var side = raceSide(day, state);
    if (hidesExercises(day, side)) return [];
    if (day.choice && day.choice.required) {
      var pick = chosenOption(day, state);
      return pick ? [pick.name] : [];
    }
    var names = [];
    var list = day.exercises || [];
    var i;
    for (i = 0; i < list.length; i += 1) names.push(list[i].name);
    return names;
  }

  function logLine(entry) {
    if (!entry) return "";
    return STATUS[entry.status] || "";
  }

  function wheelStep(view, dir) {
    var next;
    if (view.mode === "help") {
      if (!view.atEdge) return { action: "scroll" };
      return { action: "close" };
    }
    if (view.mode === "choice") {
      next = view.index + dir;
      if (next < 0 || next >= view.count) return { action: "date" };
      return { action: "choice", index: next };
    }
    if (view.mode === "race") {
      if (dir > 0) {
        if (view.raceSide === "wed") return { action: "race", raceSide: "sat" };
        return { action: "close" };
      }
      if (view.raceSide === "sat") return { action: "race", raceSide: "wed" };
      return { action: "close" };
    }
    if (!view.atEdge) return { action: "scroll" };
    return { action: "date" };
  }

  function present(day, state) {
    var side = raceSide(day, state);
    var pick = chosenOption(day, state);
    var choosing = !!(day.choice && day.choice.required && !pick);
    var start = isStart(day, side);
    return {
      choosing: choosing,
      options: choiceOptions(day),
      pick: pick,
      raceSide: side,
      replaced: start,
      raceText: start ? RACE_TEXT : "",
      volume: volumeNote(day, side),
      hideExercises: hidesExercises(day, side),
      names: exerciseNames(day, state),
      log: state["log:" + day.date] || null,
    };
  }

  return {
    CYCLE_START: CYCLE_START,
    FIRST_OPEN: FIRST_OPEN,
    CYCLE_END: CYCLE_END,
    RACE_TEXT: RACE_TEXT,
    VOLUME_TEXT: VOLUME_TEXT,
    EARLY_TEXT: EARLY_TEXT,
    LATE_TEXT: LATE_TEXT,
    todayISO: todayISO,
    addDays: addDays,
    mondayOf: mondayOf,
    screenFor: screenFor,
    shiftCursor: shiftCursor,
    choiceOptions: choiceOptions,
    needsChoice: needsChoice,
    chosenOption: chosenOption,
    raceKey: raceKey,
    raceSide: raceSide,
    hidesExercises: hidesExercises,
    volumeNote: volumeNote,
    exerciseNames: exerciseNames,
    logLine: logLine,
    wheelStep: wheelStep,
    present: present,
  };
})();
