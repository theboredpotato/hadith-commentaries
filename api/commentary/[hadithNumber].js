const fs = require('fs/promises');
const path = require('path');

module.exports = async (req, res) => {
  try {
    // Vercel passes the URL parameter in req.query
    const hadithNumber = req.query.hadithNumber;
    
    // process.cwd() points to the root of your project in Vercel
    const bukhariRoot = path.join(process.cwd(), 'data', 'fath_al_bari');
    const bookDirs = await fs.readdir(bukhariRoot, { withFileTypes: true });
    
    for (const dirent of bookDirs) {
      if (!dirent.isDirectory()) continue;
      
      const bookDir = path.join(bukhariRoot, dirent.name);
      const files = await fs.readdir(bookDir);
      const babJsonFiles = files.filter(f => /^bab-\d+\.json$/i.test(f));
      
      for (const file of babJsonFiles) {
        const fullPath = path.join(bookDir, file);
        const raw = await fs.readFile(fullPath, 'utf-8');
        const data = JSON.parse(raw);
        
        if (Array.isArray(data.hadith_numbers) && data.hadith_numbers.includes(Number(hadithNumber))) {
          const commentaryPath = path.join(bookDir, data.commentary_file);
          const commentary = await fs.readFile(commentaryPath, 'utf-8');
          
          return res.status(200).json({
            babNumber: data.bab_number,
            babTitle: data.bab_title,
            hadithNumbers: data.hadith_numbers,
            commentary
          });
        }
      }
    }
    
    return res.status(404).json({ error: 'Commentary not found for this hadith.' });
  } catch (error) {
    console.error('Error:', error.message);
    return res.status(500).json({ error: 'Internal server error.' });
  }
};