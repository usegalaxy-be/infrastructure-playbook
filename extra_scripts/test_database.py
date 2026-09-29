import sys
import psycopg2
conn = psycopg2.connect(host="",port='',database="", user="", sslmode="disable",password="")

cursor = conn.cursor()
#cursor.execute("""SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'""")
#for table in cursor.fetchall():
#    print(table)

#sql = """ UPDATE tool_shed_repository
#                SET uninstalled = %s, status= %s
#                WHERE id = %s"""
#
#cursor.execute(sql, ('True','Uninstalled', '7'))
#updated_rows = cursor.rowcount
#print updated_rows
#conn.commit()
#cursor.close()
#sys.exit()


#'id', 'create_time', 'update_time', 'tool_shed', 'name', 'description', 'owner', 'changeset_revision', 'deleted', 'metadata', 'includes_datatypes', 'installed_changeset_revision', 'uninstalled', 'dist_to_shed', 'ctx_rev', 'status', 'error_message', 'tool_shed_status'

#cursor.execute("UPDATE tool_shed_repository SET uninstalled=True, status=Uninstalled WHERE id=6")
#sys.exit()

cursor.execute("SELECT * FROM galaxy_user")
#cursor.execute("select column_name, data_type, character_maximum_length FROM INFORMATION_SCHEMA.COLUMNS where table_name = 'galaxy_user';")
#colnames = [desc[0] for desc in cursor.description]
#print colnames
#sys.exit()
#row = cursor.fetchone()
#while row:
   # do something with row
#   print row
#   row = cursor.fetchone()

#for table in cursor.fetchall():
#    print(table)

#my_table    = pd.read_sql('select * from my-table-name', connection)
#another_attempt= psql.read_sql("SELECT * FROM genome_index_tool_data", conn)


# OR
#print(another_attempt)


