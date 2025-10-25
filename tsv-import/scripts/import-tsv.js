import { PrismaClient } from '@prisma/client';
import { parse } from 'csv-parse/sync';
import { promises as fs } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const prisma = new PrismaClient();

async function importTsvFile(filePath) {
  console.log(`Processing ${filePath}...`);

  const content = await fs.readFile(filePath, 'utf-8');

  // Parse TSV file
  const records = parse(content, {
    columns: true,
    delimiter: '\t',
    skip_empty_lines: true,
    relax_quotes: true,
    relax_column_count: true
  });

  let importedCount = 0;
  let skippedCount = 0;

  for (const record of records) {
    try {
      // Generate character_id: 資料番号 + 資料内漢字番号
      const bookId = record['資料番号'];
      const indexInBook = record['資料内漢字番号'];
      const wordIndexInBook = record['資料内漢語番号'];

      if (!bookId || !indexInBook) {
        console.warn(`Skipping record with missing book_id or index_in_book`);
        skippedCount++;
        continue;
      }

      const characterId = `${bookId}_${indexInBook}`;
      const wordId = wordIndexInBook ? `${bookId}_${wordIndexInBook}` : characterId;

      // Parse integer fields, handle empty strings
      const parseIntOrNull = (value) => {
        if (!value || value.trim() === '') return null;
        const parsed = parseInt(value, 10);
        return isNaN(parsed) ? null : parsed;
      };

      const data = {
        character_id: characterId,
        book_id: bookId || null,
        book_name: record['資料名'] || null,
        index_in_book: parseIntOrNull(indexInBook),
        word_index_in_book: parseIntOrNull(wordIndexInBook),
        character: record['単字_見出し'] || null,
        character_original: record['単字_出現形'] || null,
        word_id: wordId,
        word: record['漢語_見出し'] || null,
        word_original: record['漢語_出現形'] || null,
        word_alphabet: record['漢語_alphabet'] || null,
        word_type: record['語種'] || null,
        pos_in_word: parseIntOrNull(record['漢語内位置']),
        len: record['単字長'] || null,
        shoten: record['声点'] || null,
        shoten_word: record['声点型'] || null,
        kana: record['仮名注'] || null,
        word_kana: record['仮名型'] || null,
        fanqie: record['反切'] || null,
        ruion: record['類音'] || null,
        hakase: record['節博士'] || null,
        etc: record['その他'] || null,
        position_in_book: record['出現位置'] || null,
        notes: record['備考'] || null
      };

      // Upsert: insert or update if exists
      await prisma.dhsjr.upsert({
        where: { character_id: characterId },
        update: data,
        create: data
      });

      importedCount++;
    } catch (error) {
      console.error(`Error importing record:`, error.message);
      skippedCount++;
    }
  }

  console.log(`Completed ${filePath}: ${importedCount} imported, ${skippedCount} skipped`);
  return { imported: importedCount, skipped: skippedCount };
}

async function main() {
  try {
    const dataDir = join(__dirname, '../..', 'data');
    const files = await fs.readdir(dataDir);
    const tsvFiles = files.filter(f => f.endsWith('.tsv'));

    console.log(`Found ${tsvFiles.length} TSV files to import`);

    let totalImported = 0;
    let totalSkipped = 0;

    for (const file of tsvFiles) {
      const filePath = join(dataDir, file);
      const { imported, skipped } = await importTsvFile(filePath);
      totalImported += imported;
      totalSkipped += skipped;
    }

    console.log('\n=== Import Summary ===');
    console.log(`Total records imported: ${totalImported}`);
    console.log(`Total records skipped: ${totalSkipped}`);
    console.log('Import completed successfully!');
  } catch (error) {
    console.error('Import failed:', error);
    process.exit(1);
  } finally {
    await prisma.$disconnect();
  }
}

main();
