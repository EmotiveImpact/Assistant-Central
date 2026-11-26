// The phone app reuses the web app's pure projection modules (what Home says, the queue,
// team missions, invites, the QR encoder, review checks) straight from the repository, so the
// phone and the desktop always agree. Metro only needs to be allowed to read those folders.
const path = require('path');
const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);
const repo = path.resolve(__dirname, '..');
config.watchFolders = [...(config.watchFolders || []), path.join(repo, 'workspace_ui'), path.join(repo, 'pilot', 'web')];
if (!config.resolver.sourceExts.includes('mjs')) config.resolver.sourceExts.push('mjs');
config.resolver.nodeModulesPaths = [path.join(__dirname, 'node_modules')];

module.exports = config;
