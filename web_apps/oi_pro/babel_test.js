const fs = require('fs');
const content = fs.readFileSync('pcr.html', 'utf8');
const match = content.match(/<script type="text\/babel">([\s\S]*?)<\/script>/);
console.log(match ? match[1].substring(0, 100) : "No match");
