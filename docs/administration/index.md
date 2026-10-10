### Hosting

The site is published at [cpp.social](https://cpp.social/) through GitHub Pages from [cppsocial/site](https://github.com/cppsocial/site).
The deployment workflow also triggers a separate [mirror repository](https://github.com/cppsocial/cppsocial.github.io).

To manually redeploy, rerun the [build-deploy.yaml](https://github.com/cppsocial/site/actions/workflows/build-deploy.yaml) workflow.

> [!WARNING]
> **Redeploying manually**
>
> Make sure to only ever run the build-deploy.yaml workflow on `master`. Deploying from other branches interferes with our metadata handling and may break the page.

### Pull request previews

Pull request previews are opt-in because the preview builds code from the pull request.
After reviewing the change, a repository collaborator with write access can comment `/preview` on the pull request.
The workflow records the current pull request commit, refreshes only metadata selected by changed curated records, builds without repository secrets, and deploys the resulting artifact to `https://pr-<number>--cppsocial.netlify.app`.

The deploy uses the `netlify-preview` environment, never `github-pages`.
On success, the workflow comments with the preview URL and Netlify CLI output.

### Tokens & Mirror

The content of the primary site is mirrored onto [cppsocial.github.io](https://cppsocial.github.io) via Github actions. This is a separate repository (and just republishes the build artifacts from the primary repo) to prevent Github from redirecting to cpp.social.

To facilitate this, there's two PATs in place:
- `GH_IO_MIRROR` gives [cppsocial/site](https://github.com/cppsocial/site) R/W access to actions in [cppsocial/cppsocial.github.io](https://github.com/cppsocial/cppsocial.github.io).
  This is used to start the mirroring action after a successful site built.
- `GH_IO_SOURCE` gives [cppsocial/cppsocial.github.io](https://github.com/cppsocial/cppsocial.github.io) read access to [cppsocial/site](https://github.com/cppsocial/site)'s action artifacts

These might need updating every now and then.


### Adding Maintainers/Curators

Checklist:

- Add new maintainer or curator to [MAINTAINERS.md](https://github.com/cppsocial/site/blob/master/MAINTAINERS.md)
- Invite them to the cppsocial organization [here](https://github.com/orgs/cppsocial/people)
- Add them to the appropriate teams (always add Maintainers to the Curator team as well!)

> [!NOTE]
> **MAINTAINERS.md Changes**
>
> New maintainers/curators may add themselves to MAINTAINERS.md and are encouraged to do so.
>
> If we instead open that PR for them, make sure they approve the PR before merging.
