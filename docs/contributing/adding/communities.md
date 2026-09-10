### Chat, forum, and Q&A communities

Add chat communities to the `cards` list in `content/communities/im.yaml` and forums or Q&A sites to the `cards` list in `content/communities/forums.yaml`.
Every `community_id` must be unique and must not change after publication.

```yaml
- community_id: example-community
  metadata_source: {source: web, key: 'https://example.org/community/'}
  title: Example C++ Community
  platform: forum
  path: https://example.org/community/
  description: Public forum for C++ library design and implementation questions
```

Allowed `platform` values are `discord`, `slack`, `irc`, `reddit`, and `forum`.
Allowed metadata sources are `discord`, `web`, `reddit`, and `stackoverflow`.
For `web`, the key is the canonical page URL; for Reddit, it is the subreddit name without `r/`.
For Stack Overflow, use the encoded tag `c%2B%2B` as the key.

Communities must be public, active, and substantially about C++.
Use a direct community URL and a description of its audience or focus.

### Discord

> [!IMPORTANT]
> **Non-expiring, non-vanity invites only**
>
> Use an active invite with no expiry. Server vanity or custom invites are not accepted.

Copy the code after `discord.gg/` from the community's invite, or [create an invite](https://support.discord.com/hc/en-us/articles/208866998-Invites-101) with expiry set to **Never** if you have permission.
Use that code as both the URL suffix and metadata key:

```yaml
- community_id: example-discord
  metadata_source: {source: discord, key: Ab3dE9xYz2}
  title: Example C++ Discord
  platform: discord
  path: https://discord.gg/Ab3dE9xYz2
  description: Public chat for C++ developers working on embedded systems
```

The PR check uses Discord's API to check that the invite resolves, has no expiry, and is not the server's vanity code.
Open it to confirm that it leads to the intended community.

### Check the result

For a new community, fetch only its metadata, then build:

```sh
make communities ID=example-community
make build
```

For Meetup groups, run `make events`, then `make build` and inspect `/events/`.
This refreshes all configured event feeds; leave unrelated changes out of the PR.
See [Generated files](#start) for when to include updater output.
