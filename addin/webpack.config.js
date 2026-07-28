const path = require('path');
const HtmlWebpackPlugin = require('html-webpack-plugin');

/**
 * Bundle configuration for the TEEA task pane.
 *
 * No CDN, no remote chunk loading, no source-map upload. Everything the pane
 * needs is emitted into `dist/` so it starts on an air-gapped machine (ADR-002).
 */
module.exports = (_env, argv) => {
  const isProduction = argv.mode === 'production';
  return {
    entry: {
      taskpane: './src/taskpane/index.tsx',
    },
    output: {
      path: path.resolve(__dirname, 'dist'),
      filename: '[name].js',
      clean: true,
      // Relative, so the bundle works from a file:// manifest as well as from
      // the dev server.
      publicPath: '',
    },
    resolve: {
      extensions: ['.ts', '.tsx', '.js'],
      alias: {
        '@': path.resolve(__dirname, 'src'),
      },
    },
    module: {
      rules: [
        {
          test: /\.tsx?$/,
          use: {
            loader: 'ts-loader',
            options: {
              transpileOnly: false,
              // tsconfig.json sets `noEmit: true` for `tsc --noEmit` type-check
              // runs; ts-loader needs the compiler to actually emit JS for
              // webpack to bundle, so that one option is overridden here rather
              // than duplicated into a second tsconfig file.
              compilerOptions: { noEmit: false },
            },
          },
          exclude: /node_modules/,
        },
      ],
    },
    plugins: [
      new HtmlWebpackPlugin({
        template: './src/taskpane/taskpane.html',
        filename: 'taskpane.html',
        chunks: ['taskpane'],
      }),
    ],
    devtool: isProduction ? false : 'inline-source-map',
    devServer: {
      static: { directory: path.resolve(__dirname, 'dist') },
      // Loopback only. The pane must never be reachable from another machine,
      // even in development.
      host: '127.0.0.1',
      port: 3000,
      server: 'https',
      hot: false,
    },
    performance: {
      // The pane is held to a 500 MB runtime ceiling; the bundle itself is
      // budgeted far below that, and a regression should be loud.
      maxEntrypointSize: 1_500_000,
      maxAssetSize: 1_500_000,
      hints: isProduction ? 'error' : false,
    },
  };
};
