const fs = require('fs');
const babel = require('@babel/core');
const content = fs.readFileSync('/home/sumit/upstox_kotak/web_apps/oi_pro/strike_greeks.html', 'utf8');
const scriptContent = content.split('<script type="text/babel">')[1].split('</script>')[0];
try {
    babel.transformSync(scriptContent, { presets: ['@babel/preset-react'] });
    console.log("Syntax is valid");
} catch (e) {
    console.log("SYNTAX ERROR:");
    console.error(e.message);
}
