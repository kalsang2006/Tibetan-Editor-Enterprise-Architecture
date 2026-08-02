const path = require("path");
const fs = require("fs");
const os = require("os");
const webpack = require("webpack");
const HtmlWebpackPlugin = require("html-webpack-plugin");

/**
 * Load REACT_APP_* variables from `.env` and merge with process.env.
 * This makes `process.env.REACT_APP_MONLAM_API_KEY` (and friends) available
 * at build time via DefinePlugin — without it the browser bundle crashes with
 * `Uncaught ReferenceError: process is not defined` (OCRPanel, TTS hook, etc.).
 */
function loadEnvVariables() {
  const envPath = path.resolve(__dirname, ".env");
  const envVars = {};
  if (fs.existsSync(envPath)) {
    const lines = fs.readFileSync(envPath, "utf-8").split(/\r?\n/);
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const eqIdx = trimmed.indexOf("=");
      if (eqIdx === -1) continue;
      const key = trimmed.slice(0, eqIdx).trim();
      const value = trimmed.slice(eqIdx + 1).trim();
      envVars[key] = value;
    }
  }
  // Merge: process.env overrides .env file (so CI can set vars without editing .env)
  const merged = { ...envVars };
  for (const [key, value] of Object.entries(process.env)) {
    if (key.startsWith("REACT_APP_")) {
      merged[key] = value;
    }
  }
  return merged;
}

/**
 * Bundle configuration for the TEEA task pane.
 *
 * No CDN, no remote chunk loading, no source-map upload. Everything the pane
 * needs is emitted into `dist/` so it starts on an air-gapped machine (ADR-002).
 */
module.exports = (_env, argv) => {
  const isProduction = argv.mode === "production";
  const envVars = loadEnvVariables();

  // Dynamic cross-platform dev cert resolution (ADR-002)
  const certDir = process.env.OFFICE_ADDIN_DEV_CERTS_DIR || path.join(os.homedir(), ".office-addin-dev-certs");
  const keyPath = path.join(certDir, "localhost.key");
  const certPath = path.join(certDir, "localhost.crt");

  let httpsOptions = undefined;
  if (fs.existsSync(keyPath) && fs.existsSync(certPath)) {
    httpsOptions = {
      key: fs.readFileSync(keyPath),
      cert: fs.readFileSync(certPath),
    };
  }

  // Build a stringified map of process.env variables for DefinePlugin
  const fullEnv = {
    NODE_ENV: isProduction ? "production" : "development",
    ...envVars,
  };
  const defineEnv = {
    "process.env": JSON.stringify(fullEnv),
  };
  for (const [key, value] of Object.entries(fullEnv)) {
    defineEnv[`process.env.${key}`] = JSON.stringify(value);
  }

  return {
    entry: {
      taskpane: "./src/taskpane/index.tsx",
    },

    output: {
      path: path.resolve(__dirname, "dist"),
      filename: "[name].js",
      clean: {
        // Keep the local office.js bundle across rebuilds (ADR-002 —
        // offline-first; the CDN is not reachable on an air-gapped machine).
        keep: /office\.js$/,
      },
      // Relative, so the bundle works from a file:// manifest as well as from
      // the dev server.
      publicPath: "",
    },

    resolve: {
      extensions: [".ts", ".tsx", ".js"],
      alias: {
        "@": path.resolve(__dirname, "src"),
      },
    },

    module: {
      rules: [
        {
          test: /\.tsx?$/,
          use: {
            loader: "ts-loader",
            options: {
              transpileOnly: false,
              // tsconfig.json sets `noEmit: true` for `tsc --noEmit` type-check
              // runs; ts-loader needs the compiler to actually emit JS for
              // webpack to bundle, so that one option is overridden here rather
              // than duplicated into a second tsconfig file.
              compilerOptions: {
                noEmit: false,
              },
            },
          },
          exclude: /node_modules/,
        },
      ],
    },

    plugins: [
      // Inject REACT_APP_* env vars so `process.env.REACT_APP_MONLAM_API_KEY`
      // is replaced at build time with the actual string value.
      new webpack.DefinePlugin(defineEnv),
      new HtmlWebpackPlugin({
        template: "./src/taskpane/taskpane.html",
        filename: "taskpane.html",
        chunks: ["taskpane"],
        // Inject taskpane.js at the end of <body>, guaranteeing that office.js
        // (loaded in <head>) is fully parsed before the React bundle executes.
        inject: "body",
      }),
      {
        apply: (compiler) => {
          compiler.hooks.thisCompilation.tap("CopyOfficeJsPlugin", (compilation) => {
            const officeJsPath = path.resolve(__dirname, "src/taskpane/office.js");
            if (fs.existsSync(officeJsPath)) {
              const content = fs.readFileSync(officeJsPath);
              compilation.emitAsset("office.js", new webpack.sources.RawSource(content));
            }
          });
          compiler.hooks.thisCompilation.tap("CopyAssetsPlugin", (compilation) => {
            const assetsDir = path.resolve(__dirname, "assets");
            if (fs.existsSync(assetsDir)) {
              for (const file of fs.readdirSync(assetsDir)) {
                const filePath = path.join(assetsDir, file);
                if (fs.statSync(filePath).isFile()) {
                  const content = fs.readFileSync(filePath);
                  compilation.emitAsset(`assets/${file}`, new webpack.sources.RawSource(content));
                }
              }
            }
          });
        },
      },
    ],

    devtool: isProduction ? false : "inline-source-map",

    devServer: {
      static: {
        directory: path.resolve(__dirname, "dist"),
      },
      host: "localhost",
      port: 3000,
      hot: false,
      server: {
        type: "https",
        options: httpsOptions,
      },
    },

    performance: {
      // The pane is held to a 500 MB runtime ceiling; the bundle itself is
      // budgeted far below that, and a regression should be loud.
      maxEntrypointSize: 1_500_000,
      maxAssetSize: 1_500_000,
      hints: isProduction ? "error" : false,
    },
  };
};