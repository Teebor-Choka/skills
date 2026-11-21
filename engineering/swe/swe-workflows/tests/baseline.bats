#!/usr/bin/env bats
# The shipped default procedure keeps its shape: floor stages, declared policy keys.

setup() {
  BASELINE="$BATS_TEST_DIRNAME/../procedures/sw-development.md"
}

@test "the baseline floor stages are spec and review, and nothing upstream of them is conditional" {
  run grep -c "floor: true" "$BASELINE"
  [ "$output" = "2" ]
  run grep -n "when:" "$BASELINE"
  [ "$status" -ne 0 ]
}

@test "every policy key a stage uses is declared in the policy map" {
  declared=$(awk '/^policy:/{f=1;next} /^[a-z]/{f=0} f{gsub(/:.*/,"");gsub(/ /,"");print}' "$BASELINE" | sort -u)
  used=$(grep -E '^    uses:' "$BASELINE" | sed 's/.*\[//;s/\].*//;s/,/\n/g;s/ //g' | sort -u)
  for k in $used; do
    echo "$declared" | grep -qx "$k" || { echo "undeclared: $k"; return 1; }
  done
}
