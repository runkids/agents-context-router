# Changelog

## [0.2.0](https://github.com/runkids/agents-context-router/compare/v0.1.1...v0.2.0) (2026-10-29)


### Features

* let check skip bulky directories ([b421c23](https://github.com/runkids/agents-context-router/commit/b421c23429dddd38b88a301191030466c850774f))


### Bug Fixes

* respect skipped files on the path to a nested wiki
* keep walking the path to a nested wiki ([6be83de](https://github.com/runkids/agents-context-router/commit/6be83deb6a473173654dbcde25548ba840a2c348))


### Performance Improvements

* skip directories no indexed pattern can reach ([56054f5](https://github.com/runkids/agents-context-router/commit/56054f5cadd1cffa283fcff221749dbf89d84ba8))

## [0.1.1](https://github.com/runkids/agents-context-router/compare/v0.1.0...v0.1.1) (2026-10-29)


### Bug Fixes

* find the repo when the script runs through a symlink ([a9c7cca](https://github.com/runkids/agents-context-router/commit/a9c7cca38932ad8cdb2c453a12c82bf74d2798d6))

## 0.1.0 (2026-10-29)


### Features

* add agents-context-router skill ([544a210](https://github.com/runkids/agents-context-router/commit/544a2104cfecd5d4a5fc9e992b14b2992a5b143d))
* add Claude and Codex plugin install paths ([037f16b](https://github.com/runkids/agents-context-router/commit/037f16b6dc1be9d4506839b737a6e46b9fd01435))
* add Pi, Hermes, Kimi, Muse and Cursor plugin manifests ([33e4c4e](https://github.com/runkids/agents-context-router/commit/33e4c4ee632b9d889d43153671bf431766868606))
* add the Codex plugin manifest ([e7d6d37](https://github.com/runkids/agents-context-router/commit/e7d6d37f85d98dbb44cfd2e4e037e0a592668860))
* add versioned releases and maintainer skills ([4d9287d](https://github.com/runkids/agents-context-router/commit/4d9287d062a753984dbaf9f47e9146bb57d94374))
* check indexed pages outside the wiki ([59dbd5a](https://github.com/runkids/agents-context-router/commit/59dbd5ab25090dadf9cc4d29bbb75ab4a66c0e50))
* **check:** detect undiscoverable indexed pages ([ca0c95e](https://github.com/runkids/agents-context-router/commit/ca0c95ee21fd2d205695b45dc95e6cc35a700ebb))
* **check:** validate relative Markdown file links ([632f7f8](https://github.com/runkids/agents-context-router/commit/632f7f8f5d41d03de465f2d33d7c8f1b498a287d))
* support shared router config and unrouted globs ([3600d35](https://github.com/runkids/agents-context-router/commit/3600d3532be8128564a9a0c6d2b50219b694354b))
* support shared router installs and unrouted globs ([6c45ec5](https://github.com/runkids/agents-context-router/commit/6c45ec5e836c24e64e995f0afc0962062071769f))


### Bug Fixes

* catch broken relative Markdown file links ([b0a90d1](https://github.com/runkids/agents-context-router/commit/b0a90d130c87dbe5e8e71cf635a11997e04fe5d4))
* **check:** bind Markdown blocks to their containing scope ([5775145](https://github.com/runkids/agents-context-router/commit/57751454b381a32d0ad30de826d291a336707751))
* **check:** cover block boundaries and invalid wiki inputs ([1501710](https://github.com/runkids/agents-context-router/commit/1501710a70e83145431d03afe276f6a1edcdd4d4))
* **check:** handle Markdown contexts and source aliases ([7181d20](https://github.com/runkids/agents-context-router/commit/7181d208318b7fc6add1d31810827f1cec22f61f))
* **check:** measure container indentation in columns ([842f8d5](https://github.com/runkids/agents-context-router/commit/842f8d50090a041e0cdb8ae71ffb2bd588e02f18))
* **check:** resolve inline Markdown tokens in source order ([e07e3ea](https://github.com/runkids/agents-context-router/commit/e07e3eab51f809e4385b0bd5127f51051e2ea3fd))
* **check:** respect Markdown block and container boundaries ([aa7a470](https://github.com/runkids/agents-context-router/commit/aa7a470f81fe216f88c7dffe8dd147becd923901))
* **check:** scan indexed pages across repository directories ([da3f3a2](https://github.com/runkids/agents-context-router/commit/da3f3a26ff76b5ed7ed600e450f406fe812e5e0f))
* **check:** validate links in indexed pages ([a5dee97](https://github.com/runkids/agents-context-router/commit/a5dee973771243a564dbbccfab944abace4d5e51))
* honor unrouted globs for indexed pages ([b0508dc](https://github.com/runkids/agents-context-router/commit/b0508dc7d0ab972db55eae59f5570b1c0a97766d))
* make ai-context.py work on Windows consoles and paths ([1bca50a](https://github.com/runkids/agents-context-router/commit/1bca50a698cf791afd9695e7d7b3071cf93022be))
* normalize walked paths in the orphan check ([26c0b40](https://github.com/runkids/agents-context-router/commit/26c0b4020269ba0597ce94f441137573691cf55d))
* normalize Windows router diagnostic paths ([8a74d2c](https://github.com/runkids/agents-context-router/commit/8a74d2c4a8ba0e99dbdd5a3bfefda2805a6de7ca))
* pick a working Python command on Windows and encode stderr as UTF-8 ([593f1f2](https://github.com/runkids/agents-context-router/commit/593f1f2b3f58f66a980f84cf423fd6db9a14af90))
* preserve shared-install behavior in link checks ([c156896](https://github.com/runkids/agents-context-router/commit/c156896cffe281803d8183d538dc5f5af74b4ff9))
* **router:** bound ordered list marker digits ([8d4c586](https://github.com/runkids/agents-context-router/commit/8d4c586e3d731cdb2a29d2fe9612df99e2abec90))
* **router:** decode markdown entities and nested quotes ([e6772c9](https://github.com/runkids/agents-context-router/commit/e6772c9afe64be8b1c18819a8e02f19c5a67107a))
* **router:** handle list padding html and wiki aliases ([457ff6a](https://github.com/runkids/agents-context-router/commit/457ff6abd3a498a1b11931285dc3307e2a8903de))
* **router:** parse nested list fences and escaped labels ([7ff2309](https://github.com/runkids/agents-context-router/commit/7ff2309610b136f188b0f87aa1b5ae173c7472a7))
* **router:** parse same-line nested list markers ([0de27ba](https://github.com/runkids/agents-context-router/commit/0de27bab41ff734c839c65b813fb0b974f02295a))
* **router:** preserve heading fences and tighten link tests ([8b32e7d](https://github.com/runkids/agents-context-router/commit/8b32e7db9758e96501fd1133e4f8e349eee17979))
* **router:** preserve lazy links and bound definition scans ([a1ec846](https://github.com/runkids/agents-context-router/commit/a1ec84671ed23cf6ce9bcabc942dba656a6bd948))
* **router:** preserve lazy list paragraph links ([1af45d9](https://github.com/runkids/agents-context-router/commit/1af45d936ad8de84dcec1dc6f82bfa084fc27b84))
* **router:** preserve outer quote indentation ([b239545](https://github.com/runkids/agents-context-router/commit/b2395455bdf8582c159142472e8ff4eee1630f1f))
* **router:** preserve physical quote depth for blocks ([cef9bf6](https://github.com/runkids/agents-context-router/commit/cef9bf62960774d3719b7cca88ef1cdc7566744a))
* **router:** recognize bare empty list items ([b4519c2](https://github.com/runkids/agents-context-router/commit/b4519c29c65364873f00ac170a87a4b2df6fe2e7))
* **router:** require whitespace before link titles ([8ad8a14](https://github.com/runkids/agents-context-router/commit/8ad8a14900664d7aebba1a93bf92a868ce2c36c4))
* **router:** respect list interruption rules ([fd22ced](https://github.com/runkids/agents-context-router/commit/fd22ced4b0121268f8f047cb0724869a83d30c5b))
* **router:** restrict destination escapes to punctuation ([5c48033](https://github.com/runkids/agents-context-router/commit/5c480337d4d754c6018b6fcd582cf71a054918a0))
* **router:** retain list indentation in nested quotes ([b0ed8f3](https://github.com/runkids/agents-context-router/commit/b0ed8f34158c4e8ac73835fbaf9edc03d809c893))
* **router:** stop reference titles at block boundaries ([5b373ec](https://github.com/runkids/agents-context-router/commit/5b373ec3001ee3296373b8ea0967744bd9f3742e))
* **router:** validate early reads and normalize link paths ([a6dd391](https://github.com/runkids/agents-context-router/commit/a6dd39109b5b1af57d406952075e6f34a5912401))
* **router:** validate router paths and title closers ([4590535](https://github.com/runkids/agents-context-router/commit/45905357f1d3bb6eaaad03c3e927577e47a806f7))


### Documentation

* specify initial release version ([53f03c9](https://github.com/runkids/agents-context-router/commit/53f03c97ee8cbcd90b6d256d294329a03df4eb8d))

## Changelog

Release entries are maintained by Release Please from Conventional Commits.
`0.0.0` is the unreleased bootstrap baseline, not a published release.
