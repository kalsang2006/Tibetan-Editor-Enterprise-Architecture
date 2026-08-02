/**
 * Office.js & Word.js bootstrap stub — LAST-RESORT offline initialization (ADR-002).
 *
 * This file is NOT the real Office.js library. It exists so the task pane can
 * initialize on an air-gapped machine where the Microsoft CDN
 * (https://appsforoffice.microsoft.com/lib/1/hosted/office.js) is unreachable.
 * It deliberately provides NO real Word API surface: in this mode document
 * reads and edits are unavailable, and `readDocumentText` exhausts its tiers
 * and returns "" (it logs exactly what it tried to the console).
 *
 * Load order in taskpane.html:
 *   1. https://appsforoffice.microsoft.com/lib/1/hosted/office.js  (the real
 *      library — the only supported way to talk to the Word host)
 *   2. this stub
 *
 * The guards below are the critical part. When the real Office.js loaded, the
 * stub must do NOTHING — in particular it must NOT install its dummy `Word`
 * global. A fake `Word.run` would shadow the real Word API that the host
 * injects and make `readDocumentText` see an empty document, killing every
 * suggestion. That is exactly the bug this rewrite fixes: the dummy `Word` is
 * now only installed together with the dummy `Office` (i.e. only when we are
 * in full offline-fallback mode and no real library is present at all).
 */
(function (global) {
  // A real Office.js (CDN or vendored) always defines `Office.onReady`, so its
  // presence is a reliable signal that the real library won the load order.
  var haveRealOffice = global.Office && typeof global.Office.onReady === "function";

  if (!haveRealOffice) {
    var HostType = {
      Word: "Word",
      Excel: "Excel",
      PowerPoint: "PowerPoint",
      Outlook: "Outlook",
      OneNote: "OneNote"
    };

    var PlatformType = {
      PC: "PC",
      OfficeOnline: "OfficeOnline",
      Mac: "Mac",
      iOS: "iOS",
      Android: "Android",
      Universal: "Universal"
    };

    var Office = {
      HostType: HostType,
      PlatformType: PlatformType,
      onReady: function (callback) {
        var info = { host: HostType.Word, platform: PlatformType.PC };
        if (typeof callback === "function") {
          setTimeout(function () {
            callback(info);
          }, 0);
        }
        return Promise.resolve(info);
      },
      initialize: function () {},
      context: {
        document: {
          getSelectedDataAsync: function (coercionType, callback) {
            if (typeof callback === "function") {
              callback({ status: "succeeded", value: "" });
            }
          }
        }
      }
    };
    global.Office = global.Office || Office;

    // Loud and early: the pane initializes, but document access will not work
    // in this mode. This is the reason readDocumentText logs empty reads below.
    console.warn(
      "[TEEA] Office.js CDN unreachable — running with the offline bootstrap stub. " +
        "Word document access is unavailable in this mode; suggestions will be empty.",
    );
  }

  // Install the Word fallback ONLY when we are in full-stub mode. The `!haveRealOffice`
  // condition is the fix: it stops the dummy `Word` from shadowing the real Word API
  // that the CDN office.js loads asynchronously on a connected machine.
  if (!haveRealOffice && (!global.Word || typeof global.Word.run !== "function")) {
    var Word = {
      run: function (batch) {
        var context = {
          document: {
            body: {
              text: "",
              load: function () {},
              paragraphs: { items: [], load: function () {} }
            },
            getSelection: function () {
              return { text: "", load: function () {}, insertText: function () {} };
            }
          },
          sync: function () { return Promise.resolve(); }
        };
        if (typeof batch === "function") {
          try {
            return Promise.resolve(batch(context));
          } catch (err) {
            return Promise.reject(err);
          }
        }
        return Promise.resolve();
      },
      InsertLocation: {
        replace: "Replace",
        after: "After",
        before: "Before",
        end: "End",
        start: "Start"
      }
    };
    global.Word = global.Word || Word;
  }
})(typeof self !== "undefined" ? self : this);
