#!/usr/bin/env bash
# 按 package.v3.json 的 history 为历史版本批量补发 GitHub Release。
#
# 宿主的版本历史弹窗只会给「存在对应 Release」的版本显示安装按钮，
# 且 Release 必须满足：tag = <插件ID>_v<版本>，资产 = <id小写>_v<版本>.zip。
# 每个版本从「索引中该插件 version 等于该版本」的 git 提交里取代码快照；
# 找不到对应提交（例如沿用 V2 说明但没有 V3 代码的记录）就跳过。
set -euo pipefail

pkg_file="package.v3.json"
max_per_plugin="${MAX_PER_PLUGIN:-10}"

mapfile -t entries < <(
  jq -r 'to_entries | map(select(.value.release == true)) | .[] | "\(.key)|\(.value.version)"' "$pkg_file"
)

for entry in "${entries[@]}"; do
  plugin_id="${entry%%|*}"
  plugin_id_lc="$(echo "$plugin_id" | tr '[:upper:]' '[:lower:]')"
  plugin_dir="plugins.v3/${plugin_id_lc}"
  if [ ! -d "$plugin_dir" ]; then
    echo "SKIP $plugin_id: directory $plugin_dir not found"
    continue
  fi

  count=0
  while read -r ver; do
    [ -n "$ver" ] || continue
    if [ "$count" -ge "$max_per_plugin" ]; then
      break
    fi
    tag="${plugin_id}_v${ver}"
    if gh release view "$tag" >/dev/null 2>&1; then
      echo "SKIP $tag: release already exists"
      count=$((count + 1))
      continue
    fi

    # 找到「索引中该插件版本等于当前目标版本」的最新提交作为代码快照
    commit=""
    while read -r candidate; do
      snapshot="$(git show "${candidate}:${pkg_file}" 2>/dev/null || true)"
      [ -n "$snapshot" ] || continue
      candidate_version="$(echo "$snapshot" | jq -r --arg p "$plugin_id" '.[$p].version // empty')"
      if [ "$candidate_version" = "$ver" ]; then
        commit="$candidate"
        break
      fi
    done < <(git rev-list --all -- "$pkg_file")

    if [ -z "$commit" ] || ! git cat-file -e "${commit}:${plugin_dir}/__init__.py" 2>/dev/null; then
      echo "SKIP $tag: no matching V3 snapshot"
      continue
    fi

    asset="${plugin_id_lc}_v${ver}.zip"
    tmp="$(mktemp -d)"
    git archive "$commit" "$plugin_dir" | tar -x -C "$tmp"
    rm -rf "${tmp}/${plugin_dir}/__pycache__" "${tmp}/${plugin_dir}/node_modules" "${tmp}/${plugin_dir}/src"
    rm -f "$asset"
    (cd "${tmp}/$(dirname "$plugin_dir")" && zip -qr "$GITHUB_WORKSPACE/$asset" "$(basename "$plugin_dir")") || true
    if [ ! -s "$asset" ]; then
      echo "SKIP $tag: empty package"
      rm -rf "$tmp"
      continue
    fi

    notes="$(jq -r --arg p "$plugin_id" --arg v "v${ver}" '.[$p].history[$v] // empty' "$pkg_file")"
    if [ -z "$notes" ]; then
      notes="Automated release of ${plugin_id} ${ver}"
    fi
    echo "CREATE $tag from $commit"
    gh release create "$tag" "$asset" --title "$tag" --notes "$notes" --target "$commit" \
      || echo "WARN: failed to create $tag"
    rm -rf "$tmp" "$asset"
    count=$((count + 1))
  done < <(
    jq -r --arg p "$plugin_id" '.[$p].history | keys_unsorted[] | ltrimstr("v")' "$pkg_file" | sort -Vr
  )
done
