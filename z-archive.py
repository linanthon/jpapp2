    # def _sep_mora_get_audio_ids(self, spelling: str) -> list:
    #     """
    #     Separate the spelling of a word (can be Higarana or Katakana)
    #     into a list of letters, return a list of audio IDs of those letters.

    #     "ん" ending problem: はん is read as "han", not "ha un".
    #     In DB there're records for all sounds of the "ん" ending combos.
    #     When see "ん", remove the latest element in list then get the combo sound.
    #     """
    #     audio_id_list = []
    #     kana_list: list = jamorasep.parse(spelling)
    #     for i, kana in enumerate(kana_list):
    #         # If kana split is "ん"
    #         if i > 0 and kana == "ん":
    #             # remove the previous audio
    #             audio_id_list = audio_id_list[:-1]
    #             # add the audio of "<previous sound> + n"
    #             new_spell = kana_list[i-1] + "ん"
    #         else:
    #             new_spell = kana
            
    #         new_audio = AUDIOS.get(new_spell)
    #         if new_audio:
    #             audio_id_list.append(new_audio)
    #         else:
    #             log.error(f"""Failed to get audio for word of spelling '{spelling}',
    #                       not found audio for '{new_spell}'""")
    #             return []

    #     return audio_id_list


    # Audio =================================================================================
    # def insert_audio(self, dirname: str = "data/audio/") -> bool:
    #     """
    #     Read audio files in "data/audio/" if exists and insert to DB if not yet.
    #     The file name should be <word>.wav, the <word> only composed of the
    #     characters in the alphabets. Return True when finish, False if got error.
    #     """
    #     for root, _, files in os.walk(dirname):
    #         for filename in files:
    #             name = filename.split(".")[0]
    #             if name:
    #                 word = name[0]
    #                 # Check already in DB
    #                 query = sql.SQL("SELECT COUNT(*) FROM {table} VALUES WHERE word = %s;"
    #                                 ).format(table=sql.Identifier(self._table_audio))
    #                 if self._safe_execute(query, (word,)):
    #                     if self._cursor.fetchone().get("count"):
    #                         continue

    #                 # Insert
    #                 with open(os.path.join(root, filename), "rb") as f:
    #                     wav_bytes = f.read()
    #                     query = sql.SQL("INSERT INTO {table} (word, sound) VALUES (%s, %s);"
    #                                     ).format(table=sql.Identifier(self._table_audio))
    #                     if self._safe_execute(query, (word, wav_bytes)):
    #                         self._conn.commit()
    #                     else:
    #                         self._conn.rollback()
    #                         return False
    #     return True
                
    # def load_audio_ids(self) -> None:
    #     """
    #     Loads audio table records into the global `AUDIOS` var:
    #     - key: romaji
    #     - value: ID
    #     """
    #     query = sql.SQL("SELECT id, word FROM {table};").format(
    #         table=sql.Identifier(self._table_audio)
    #     )
    #     if not self._safe_execute(query):
    #         return
        
    #     for row in self._cursor.fetchall():
    #         AUDIOS[row.get("word")] = row.get("id")

    # def get_audio_bytes(self, audio_ids: list) -> list:
    #     """
    #     Get audio bytes list from DB by the input IDs. Order is important.
    #     Return [] if one of the IDs is not found.
    #     """
    #     audio_bytes_list = []
    #     for aid in audio_ids:
    #         query = sql.SQL("SELECT id, sound FROM {table} WHERE id = %s;").format(
    #             table=sql.Identifier(self._table_audio)
    #         )
    #         if self._safe_execute(query, (aid,)):
    #             audio_bytes_list.append(self._cursor.fetchone()["sound"])
    #         else:
    #             audio_bytes_list = []
    #             break
    #     return audio_bytes_list
    # =======================================================================================