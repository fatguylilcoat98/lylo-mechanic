/*
 * LYLO Mechanic — withAndroidBaseColors
 *
 * This is a managed Expo project, so there is no checked-in
 * mobile/android/ directory. The Android project (including
 * app/src/main/res/values/colors.xml and styles.xml) is generated
 * by `expo prebuild` on the EAS build server.
 *
 * The preview build was failing with:
 *
 *   :app:processReleaseResources
 *   Android resource linking failed
 *   error: resource color/colorPrimary not found.
 *
 * The cause: something in the generated styles.xml (or in a library
 * that merges its own values.xml during the build) references
 * @color/colorPrimary, @color/colorPrimaryDark, and @color/colorAccent,
 * but those names are not present in the generated colors.xml for
 * this particular Expo 51 / RN 0.74 prebuild path.
 *
 * Fix: use the built-in withAndroidColors mod to guarantee those
 * three classic AppCompat color names exist in colors.xml with
 * values that match our dark theme. withAndroidColors runs AFTER
 * prebuild has generated the base file, so we're adding on top of
 * whatever Expo produces rather than replacing it.
 */

const { withAndroidColors } = require('expo/config-plugins');

function setColor(colorsRoot, name, hex) {
  if (!colorsRoot.resources) colorsRoot.resources = {};
  if (!colorsRoot.resources.color) colorsRoot.resources.color = [];
  const arr = colorsRoot.resources.color;
  const existing = arr.find(c => c && c.$ && c.$.name === name);
  if (existing) {
    existing._ = hex;
  } else {
    arr.push({ $: { name }, _: hex });
  }
}

module.exports = function withAndroidBaseColors(config) {
  return withAndroidColors(config, async (cfg) => {
    // LYLO palette from src/constants/colors.js
    //   accent  #1a8fff  -> colorPrimary / colorAccent
    //   bg      #0a0c0f  -> colorPrimaryDark (status bar tint)
    setColor(cfg.modResults, 'colorPrimary',     '#1a8fff');
    setColor(cfg.modResults, 'colorPrimaryDark', '#070b14');
    setColor(cfg.modResults, 'colorAccent',      '#1a8fff');
    return cfg;
  });
};
