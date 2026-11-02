# Golf Pro TrackMan MCP

A local MCP server that lets an AI assistant read your TrackMan activities and shot-level data. It can list recent sessions, retrieve measured and normalized shot values, and summarize results by club and drill tags.

Each user runs their own copy and signs into their own TrackMan account. This project does not operate a hosted service, receive your login, or include anyone's golf data.

**Unofficial:** not affiliated with or endorsed by TrackMan. The server uses a private TrackMan cloud API. API availability, permitted use, and authentication can change. Review TrackMan's terms before using it.

## Authentication: read before connecting

The default login configuration is derived from [apiman](https://github.com/l3wi/apiman). It uses the public client ID of TrackMan's older golf app, so the consent screen may say **“Old Golf App,” not “Golf Pro.”** This is not a dedicated registration for this project.

The default authorization scopes include `dr/simulate` and `dr/cloud`; they have **not** been established as read-only account permissions. The server's golf-data tools only issue queries, but this does not restrict what a stolen token could authorize. Review the consent screen and do not approve access you are uncomfortable granting. If TrackMan supplies a supported client registration, configure `TRACKMAN_CLIENT_ID` and `TRACKMAN_SCOPES` for it.

Passwords are entered only on TrackMan's sign-in page. The server stores access and refresh tokens locally with restricted filesystem permissions on macOS/Linux. It does not store your password. The language-model client receives requested golf data, so that client's data policies also apply.

## Requirements

- Python 3.11 or later
- Your own TrackMan Golf account with cloud activities
- An MCP client supporting local stdio servers, such as Codex
- Internet access to TrackMan

## Install

Clone this repository, open a terminal in its folder, and create a Python environment:

```sh
git clone https://github.com/devinertel/golf-pro-trackman-mcp.git
cd golf-pro-trackman-mcp
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

On Windows, use `python` instead of `python3`, and `.venv\Scripts\python.exe` instead of `.venv/bin/python`. Windows protects token files through account/directory permissions; the POSIX permission modes used on macOS/Linux do not provide an equivalent Windows ACL policy.

## Connect to Codex

From the repository folder, on macOS/Linux:

```sh
codex mcp add golf-pro-trackman -- "$PWD/.venv/bin/python" "$PWD/server.py"
```

Restart or reload your MCP client after registration if the tools are not visible. To inspect the registration:

```sh
codex mcp get golf-pro-trackman
```

For another MCP client, use a local stdio configuration with **your own absolute paths**:

```json
{
  "mcpServers": {
    "golf-pro-trackman": {
      "command": "/absolute/path/to/golf-pro-trackman-mcp/.venv/bin/python",
      "args": ["/absolute/path/to/golf-pro-trackman-mcp/server.py"]
    }
  }
}
```

On Windows, the command points to `.venv\Scripts\python.exe`; JSON backslashes must be escaped. See the [official Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp) for client settings.

## Sign in

Ask your assistant:

> Use Golf Pro TrackMan to begin login. Give me the verification link and code. I will authorize my account in TrackMan, then tell you when I am done.

The assistant calls `begin_login`. Open its returned TrackMan link yourself, check the code, and review the consent screen. After you finish, the assistant calls `finish_login`. If the response is pending, it must respect `retry_after_seconds` before polling again.

Alternatively, run:

```sh
.venv/bin/python server.py --login
```

Open the printed URL yourself; the command polls until authorized or expired. Check local status with:

```sh
.venv/bin/python server.py --status
```

Local status indicates whether saved credentials exist; it does not prove live API access. To verify access, request one activity. A browser confirmation page can show an error even after device authorization succeeds; check status and a read request before signing in again.

## Example requests

- “List my September 2026 practice sessions. Use America/Los_Angeles month boundaries.”
- “Retrieve every shot from this Virtual Range activity, following pagination.”
- “Summarize measured carry by club, including missing readings and sample standard deviation.”
- “Show normalized results separately. Keep drill tags separate from ordinary shots.”

There is no built-in coaching persona. Use the tools with your own coaching instructions. Treat lesson shots and simulated on-course shots as context-dependent observations, not automatic stock distances.

## Available tools

| Tool | Purpose |
|---|---|
| `connection_status` | Inspect local credential status without revealing tokens. |
| `begin_login` | Start device authorization; return a TrackMan verification link and code. |
| `finish_login` | Poll once and save tokens after authorization. |
| `list_activities` | List activities with date/type filters and pagination. |
| `get_session_shots` | Return shot-level measured and normalized data in source SI units. |
| `summarize_session` | Summarize shots by club metadata and tags in mph, yards, degrees, and rpm. |

### Data behavior and limitations

- Date-only filters use UTC. Supply timezone offsets when local calendar boundaries matter.
- Activity pages contain at most 100 items. Follow `next_skip` until null. Pass `kinds=[]` to list all activity kinds; the default lists shot-bearing kinds.
- Shot responses contain at most 250 shots. Follow `next_offset` until null. Every call fetches the complete activity upstream before slicing the returned page.
- Raw measurements use m/s, meters, degrees, rpm, and seconds. Summary conversions are explicit in each metric's unit field.
- Summaries include mean, median, sample standard deviation, minimum, maximum, and valid/missing counts. They exclude no outliers and never substitute measured values for missing normalized values.
- Tags and club metadata define separate summary groups. Empty tags do not prove that a shot was a full swing.
- Activity-card shot counts can differ from shots returned for the underlying session. Different activities may overlap. Do not sum them as verified unique shots.
- Club metadata may contain standard/default labels and lofts; it is not proof of the player's actual equipment.
- Normalization conditions are not inferred. Keep report-specific normalization settings separate.
- GraphQL partial results are rejected rather than silently dropping data. Upstream error bodies are not echoed.
- Dynamic-report coaching notes, lesson video analysis, and automatic scheduled syncing are not implemented.
- The server has no TrackMan mutation tools and no network listener. It communicates with its MCP client over stdio and makes outbound requests only to fixed TrackMan endpoints.

## Credential storage and sharing

By default, tokens are stored in `.private/` beside `server.py`. To choose another local directory, set `GOLF_PRO_STATE_DIR` in the server's environment. Refresh happens on demand; there is no background refresh schedule. Keep this directory out of shared/cloud-synced folders and backups you do not trust.

**Share source code, never your working account directory.** Do not share `.private`, tokens, `.env` files, golf exports, session snapshots, or personal coaching records. `.gitignore` excludes common credential/data locations, but review staged files before every push. If a credential was committed, deleting it in a later commit is insufficient: revoke it and remove it from history.

To remove the Codex registration:

```sh
codex mcp remove golf-pro-trackman
```

Removing registration does not delete cached credentials. Deleting your own `.private` cache disconnects this copy; it does not revoke TrackMan authorization. Use TrackMan's account controls or contact TrackMan to revoke authorization if needed.

This implementation uses one local account cache per process. **Do not expose it as a shared remote service.** Hosting for multiple users requires separate authentication, per-user token isolation, secure storage, and a supported TrackMan authorization approach.

## Development and tests

```sh
.venv/bin/python -m unittest discover -s . -v
```

Tests use mocked TrackMan responses plus a real local MCP stdio handshake. They cover device-login pending/slowdown/success, token permissions, token refresh, pagination, rejection of partial data, sign-in destination validation, conversions, missing values, and drill separation. Automated tests do not prove TrackMan's live API will remain compatible.

## Credits and license

GraphQL query definitions and the authentication approach are derived from [l3wi/apiman](https://github.com/l3wi/apiman), copyright Lewis Freiberg, MIT. Its license is included in [THIRD_PARTY_LICENSE.txt](THIRD_PARTY_LICENSE.txt).

MCP transport uses the [official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk). This project's code is available under the [MIT license](LICENSE).
