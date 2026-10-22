# `gh pr create` fails: "Resource not accessible by personal access token"

Seen 2026-10-22 on the development VM, opening a PR on our fork:

```
pull request create failed: GraphQL: Resource not accessible by personal access token (createPullRequest)
```

The REST call (`gh api -X POST repos/thodkatz/elixir-biohackathon-2026-test/pulls ...`) fails the same way
with HTTP 403, while `gh api repos/thodkatz/elixir-biohackathon-2026-test --jq .permissions` shows `admin: true`.
The account may do it; the token may not: `gh` here uses a fine-grained personal access token whose
repository access or *Pull requests* permission does not cover this repo. `git push` still works, because the
remotes use SSH, not the token.

Fix: give the token *Pull requests: Read and write* (and *Contents: Read*) on
`thodkatz/elixir-biohackathon-2026-test` in GitHub's token settings. Until then, push the branch and open the
PR from the URL `git push` prints (`https://github.com/thodkatz/elixir-biohackathon-2026-test/pull/new/<branch>`).
