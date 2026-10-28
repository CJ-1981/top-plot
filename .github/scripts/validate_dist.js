const fs = require('fs');
const path = require('path');

const repoRoot = path.resolve(__dirname, '..', '..');
const indexPath = path.join(repoRoot, 'index.html');
const standalonePath = path.join(repoRoot, 'top_log_analyzer_standalone.html');

console.log('Checking existence of distributable files...');
if (!fs.existsSync(indexPath)) {
  console.error('Error: index.html is missing!');
  process.exit(1);
}
if (!fs.existsSync(standalonePath)) {
  console.error('Error: top_log_analyzer_standalone.html is missing!');
  process.exit(1);
}

const indexContent = fs.readFileSync(indexPath, 'utf-8');
const standaloneContent = fs.readFileSync(standalonePath, 'utf-8');

if (indexContent.length === 0) {
  console.error('Error: index.html is empty!');
  process.exit(1);
}
if (standaloneContent.length === 0) {
  console.error('Error: top_log_analyzer_standalone.html is empty!');
  process.exit(1);
}

if (indexContent !== standaloneContent) {
  console.error('Error: index.html and top_log_analyzer_standalone.html are not in sync!');
  process.exit(1);
}

console.log('Validating critical DOM elements, version info, and scripts...');
const requiredTokens = [
  'id="btnBatchExportAll"',
  'id="batchExportModal"',
  'id="btnBatchExportZip"',
  'id="btnBatchExportFolder"',
  'id="appVersionBadge"',
  'class="app-footer"',
  'window.APP_VERSION',
  'window.BUILD_DATE',
  'dropSequenceCounter',
  'virtualPath',
  'renameSession',
  'createSimpleZip',
  'calculateCrc32',
  'Plotly'
];

for (const token of requiredTokens) {
  if (!indexContent.includes(token)) {
    console.error(`Error: Missing required token: "${token}" in index.html`);
    process.exit(1);
  }
}

console.log('✅ Validation passed: index.html and standalone distributable are verified and synchronized.');
