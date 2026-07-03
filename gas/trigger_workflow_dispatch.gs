/**
 * GitHub Actions の workflow_dispatch を Google Apps Script から実行する。
 *
 * Script Properties に以下を設定して使う:
 * - GITHUB_TOKEN: GitHub Personal Access Token
 *   - Fine-grained token: 対象repoの Actions: Read and write
 *   - classic token: private repoなら repo、public repoなら public_repo + workflow
 * - GITHUB_OWNER: ユーザー名
 * - GITHUB_REPO: リポジトリ名
 * - GITHUB_WORKFLOW_ID: workflowファイル名。例: daily-scrape.yml
 * - GITHUB_REF: 実行するbranch/tag。未設定なら main
 *
 * GAS側の時間主導トリガーは createDailyTrigger() を1回実行して作成する。
 */
const SCRIPT_TIME_ZONE = 'Asia/Tokyo';
const DEFAULT_WORKFLOW_REF = 'main';

function triggerDailyScrapeWorkflow() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30000)) {
    throw new Error('Another workflow dispatch is already running.');
  }

  try {
    const config = getGithubConfig_();
    const response = dispatchWorkflow_(config);
    console.log(
      `workflow_dispatch accepted: ${config.owner}/${config.repo} ` +
        `${config.workflowId}@${config.ref}, status=${response.getResponseCode()}`,
    );
  } finally {
    lock.releaseLock();
  }
}

function createDailyTrigger() {
  deleteDailyTriggers();
  ScriptApp.newTrigger('triggerDailyScrapeWorkflow')
    .timeBased()
    .atHour(9)
    .nearMinute(0)
    .everyDays(1)
    .inTimezone(SCRIPT_TIME_ZONE)
    .create();
}

function deleteDailyTriggers() {
  for (const trigger of ScriptApp.getProjectTriggers()) {
    if (trigger.getHandlerFunction() === 'triggerDailyScrapeWorkflow') {
      ScriptApp.deleteTrigger(trigger);
    }
  }
}

function getGithubConfig_() {
  const properties = PropertiesService.getScriptProperties();
  const token = requiredProperty_(properties, 'GITHUB_TOKEN');
  const owner = requiredProperty_(properties, 'GITHUB_OWNER');
  const repo = requiredProperty_(properties, 'GITHUB_REPO');
  const workflowId = requiredProperty_(properties, 'GITHUB_WORKFLOW_ID');
  const ref = properties.getProperty('GITHUB_REF') || DEFAULT_WORKFLOW_REF;

  return { token, owner, repo, workflowId, ref };
}

function requiredProperty_(properties, name) {
  const value = properties.getProperty(name);
  if (!value) {
    throw new Error(`Script property is missing: ${name}`);
  }
  return value;
}

function dispatchWorkflow_(config) {
  const workflowPath = encodeURIComponent(config.workflowId);
  const url =
    `https://api.github.com/repos/${config.owner}/${config.repo}` +
    `/actions/workflows/${workflowPath}/dispatches`;

  const response = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    headers: {
      Authorization: `Bearer ${config.token}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
    },
    payload: JSON.stringify({ ref: config.ref }),
    muteHttpExceptions: true,
  });

  const status = response.getResponseCode();
  if (status !== 204) {
    throw new Error(
      `workflow_dispatch failed: status=${status}, body=${response.getContentText()}`,
    );
  }

  return response;
}
