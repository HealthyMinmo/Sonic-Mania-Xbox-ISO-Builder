# RSDKv5(U) DECOMPILATION SOURCE CODE LICENSE v2.1

The code in this repository is a decompilation of RSDK (Retro-Engine) version 5 and 5-Ultimate.
There is original code in this repo, but most of the code is to be functionally the same as the version of RSDK this repo specifies.

This code is provided as-is, that is to say, without liability or warranty. 
Original authors of RSDK and authors of the decompilation are not held responsible for any damages or other claims said.

You may copy, modify, contribute, and distribute, for public or private use, **as long as the following are followed:**
- All pre-built executables provided TO ANYONE *PRIVATE OR OTHERWISE* **must be built with DLC disabled by __default.__**
  - DLC is managed by the DummyCore Usercore. A define, `RSDK_AUTOBUILD`, and a CMake flag, `RETRO_DISABLE_PLUS`, are already provided for you to force DLC off.
  - Creating a configuration setting *is allowed,* so long as it is set to off by default.
    - *No such configuration will be pushed to the master repository.*
  - This is to ensure an extra layer of legal protection for Sonic Mania Plus and Sonic Origins Plus.
- You may not use the decompilation for commercial (any sort of profit) use.
- You must clearly specify that the decompilation and original code are not yours: the developers of both must be credited.
- You may not distribute assets used to run any game not directly provided by the repository (other than unique, modded assets).
- This license must be in all modified copies of source code, and all forks must follow this license.

Original RSDK authors: Evening Star

Decompilation authors: Rubberduckycooly and chuliRMG

---

## Applicability to this repository

This tool is licensed under the RSDKv5(U) Decompilation Source Code License, reproduced
above verbatim, because `builder/rsdk.py` implements the RSDK archive format by
translating the decompilation's own reader — the key derivation and decryption routines
correspond directly to `RSDKv5/RSDK/Core/Reader.cpp` (`GenerateELoadKeys`,
`DecryptBytes`). It is a derivation of that work, not an independent implementation, so
it carries the same terms rather than a licence of this project's choosing.

In practice, for anyone using or forking this tool:

- **No commercial use.** Not for sale, and not for anything that turns a profit.
- **Credit is required.** The decompilation and the original engine are not this
  project's work; both sets of authors are credited above and in the README.
- **No game assets.** This tool distributes none. It requires a `Data.rsdk` that you
  supply from your own legitimate copy of Sonic Mania.
- **DLC defaults to off.** The Plus DLC is a configuration setting (`dlcEnabled` in
  `Settings.ini`), which this licence permits explicitly, and it ships disabled: the
  builder writes `dlcEnabled=n` unless the user deliberately ticks the checkbox, and the
  engine treats a missing file, a missing key, or an unrecognised value as off.
- **This licence travels.** It must remain in modified copies and forks.

Third-party tools used at runtime are not covered by this licence and are not
redistributed by it; see `licenses/README.md`.
