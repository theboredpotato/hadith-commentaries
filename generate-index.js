const fs = require('fs');
const path = require('path');

const bukhariRoot = path.join(__dirname, 'data', 'fath_al_bari');
const index = {};

const bookDirs = fs.readdirSync(bukhariRoot, { withFileTypes: true });
for (const bookDirent of bookDirs) {
    if (!bookDirent.isDirectory()) continue;
    const bookDir = path.join(bukhariRoot, bookDirent.name);
    const files = fs.readdirSync(bookDir);
    const babFiles = files.filter(f => f.endsWith('.json'));
    
    for (const file of babFiles) {
        const fullPath = path.join(bookDir, file);
        const data = JSON.parse(fs.readFileSync(fullPath, 'utf-8'));
        // Create the relative path so the bot knows where to fetch it
        const relativePath = path.join('data', 'fath_al_bari', bookDirent.name, file).replace(/\\/g, '/');
        
        for (const num of data.hadith_numbers) {
            index[num] = relativePath;
        }
    }
}

fs.writeFileSync(path.join(__dirname, 'index.json'), JSON.stringify(index, null, 2));
console.log('index.json generated successfully!');