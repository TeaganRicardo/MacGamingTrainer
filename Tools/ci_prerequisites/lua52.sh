#!/usr/bin/env bash
set -euo pipefail

os_name="$(uname -s)"
case "$os_name" in
  Linux)
    if [[ "$(id -u)" -eq 0 ]]; then
      apt-get update -qq
      apt-get install -y --no-install-recommends lua5.2 liblua5.2-dev
    else
      sudo apt-get update -qq
      sudo apt-get install -y --no-install-recommends lua5.2 liblua5.2-dev
    fi
    ;;
  Darwin)
    cache_root="${MGT_PREREQUISITES_CACHE_DIR:-${RUNNER_TEMP:-/tmp}/ci-prerequisites}"
    archive="$cache_root/lua-5.2.4.tar.gz"
    lua_root="$cache_root/lua-5.2.4"
    mkdir -p "$cache_root"
    if [[ -x "$lua_root/src/lua" ]] \
      && [[ -f "$lua_root/src/liblua.a" ]] \
      && [[ -f "$lua_root/src/lua.h" ]] \
      && [[ -f "$lua_root/src/lauxlib.h" ]] \
      && [[ -f "$lua_root/src/lualib.h" ]] \
      && [[ "$("$lua_root/src/lua" -e 'io.write(_VERSION)' 2>/dev/null)" == "Lua 5.2" ]]; then
      if [[ -n "${GITHUB_ENV:-}" ]]; then
        echo "MGT_LUA52=$lua_root/src/lua" >> "$GITHUB_ENV"
      fi
      exit 0
    fi
    rm -rf "$lua_root"
    mkdir -p "$lua_root"
    fetched=false
    for mirror in \
      "https://www.lua.org/ftp/lua-5.2.4.tar.gz|b9e2e4aad6789b3b63a056d442f7b39f0ecfca3ae0f1fc0ae4e9614401b69f4b" \
      "https://deb.debian.org/debian/pool/main/l/lua5.2/lua5.2_5.2.4.orig.tar.gz|86fb7e23cbbddfcd92684e5f8017ff41c9112251d1656dbece415a97fad171c0" \
      "https://archive.ubuntu.com/ubuntu/pool/universe/l/lua5.2/lua5.2_5.2.4.orig.tar.gz|86fb7e23cbbddfcd92684e5f8017ff41c9112251d1656dbece415a97fad171c0"; do
      url="${mirror%|*}"
      expected_sha="${mirror##*|}"
      # Retry transport errors across multiple verified mirrors; exact SHA-256
      # checks guarantee identical Lua 5.2.4 source regardless of mirror.
      if curl -fsSL --retry 5 --retry-all-errors --retry-delay 2 --connect-timeout 20 -o "$archive" "$url" \
        && printf '%s  %s\n' "$expected_sha" "$archive" | shasum -a 256 -c -; then
        fetched=true
        break
      fi
      rm -f "$archive"
    done
    if [[ "$fetched" != "true" ]]; then
      echo "Failed to download and verify Lua 5.2.4 from all configured mirrors." >&2
      exit 1
    fi
    tar -xzf "$archive" --strip-components=1 -C "$lua_root"
    rm -f "$archive"
    make -C "$lua_root/src" generic
    test "$("$lua_root/src/lua" -e 'io.write(_VERSION)')" = "Lua 5.2"
    if [[ -n "${GITHUB_ENV:-}" ]]; then
      echo "MGT_LUA52=$lua_root/src/lua" >> "$GITHUB_ENV"
    fi
    ;;
  *)
    echo "Unsupported OS for prerequisite lua52: $os_name" >&2
    exit 1
    ;;
esac
