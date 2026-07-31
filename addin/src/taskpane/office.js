/**
 * Vendor Office.js & Word.js stub for offline / air-gapped initialization (ADR-002).
 * Guarantees Office.onReady() fires immediately and Word API fallbacks exist when offline.
 */
(function (global) {
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

  if (!global.Office || typeof global.Office.onReady !== "function") {
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
  }

  if (!global.Word || typeof global.Word.run !== "function") {
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
