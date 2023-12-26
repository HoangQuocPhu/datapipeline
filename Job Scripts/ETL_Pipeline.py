import os
import time
import datetime
import pyspark.sql.functions as sf
from uuid import *
from pyspark.sql import SparkSession
from pyspark.sql import SQLContext
from pyspark.sql.functions import when
from pyspark.sql.functions import col
from pyspark.sql.types import *
from pyspark.sql.functions import lit
from pyspark import SparkConf, SparkContext
from uuid import * 
from uuid import UUID
import time_uuid 
from pyspark.sql import Row
from pyspark.sql.functions import udf
from pyspark.sql.functions import monotonically_increasing_id
from pyspark.sql.window import Window as W

SUBMIT_ARGS = "--packages com.databricks:spark-csv_2.11:1.2.0 pyspark-shell"
os.environ["PYSPARK_SUBMIT_ARGS"] = SUBMIT_ARGS

spark = SparkSession.builder\
    .config("spark.jars.packages","com.mysql:mysql-connector-j:8.0.30")\
    .config('spark.jars.packages', 'com.datastax.spark:>spark-cassandra-connector-assembly_2.12:3.3.0').getOrCreate()
    # .config("spark.executor.memory", "32g")\
    # .config("spark.memory.offHeap.enabled","true") \
    # .config("spark.memory.offHeap.size","10g")\
    

#read data from Cassandra 
#data = spark.read.format("org.apache.spark.sql.cassandra").options(table = 'tracking',keyspace = 'study_de').load()

#def process_df(df):
#    spark_time = df.select('create_time').collect()
#    normal_time = []
#    for i in range(len(spark_time)):
#        a = time_uuid.TimeUUID(bytes=UUID(df.select('create_time').collect()[i][0]).bytes).get_datetime().strftime(('%Y-%m-%d %H:%M:%S'))
#        normal_time.append(a)
#    spark_timeuuid = []
#    for i in range(len(spark_time)):
#        spark_timeuuid.append(spark_time[i][0])
#    time_data = spark.createDataFrame(zip(spark_timeuuid,normal_time),['create_time','ts'])
#    result = df.join(time_data,['create_time'],'inner').drop(df.ts)
#    result = result.select('create_time','ts','job_id','custom_track','bid','campaign_id','group_id','publisher_id')
#    return result
    
def calculating_clicks(df):
    clicks_data = df.filter(df.custom_track == 'click')
    clicks_data = clicks_data.na.fill({'bid':0})
    clicks_data = clicks_data.na.fill({'job_id':0})
    clicks_data = clicks_data.na.fill({'publisher_id':0})
    clicks_data = clicks_data.na.fill({'group_id':0})
    clicks_data = clicks_data.na.fill({'campaign_id':0})
    clicks_data.registerTempTable('clicks')
    clicks_output = spark.sql("""select job_id , date(ts) as date , hour(ts) as hour , publisher_id , campaign_id , group_id , avg(bid) as bid_set, count(*) as clicks , sum(bid) as spend_hour from clicks
    group by job_id , date(ts) , hour(ts) , publisher_id , campaign_id , group_id """)
    return clicks_output 
    
def calculating_conversion(df):
    conversion_data = df.filter(df.custom_track == 'conversion')
    conversion_data = conversion_data.na.fill({'job_id':0})
    conversion_data = conversion_data.na.fill({'publisher_id':0})
    conversion_data = conversion_data.na.fill({'group_id':0})
    conversion_data = conversion_data.na.fill({'campaign_id':0})
    conversion_data.registerTempTable('conversion')
    conversion_output = spark.sql("""select job_id , date(ts) as date , hour(ts) as hour , publisher_id , campaign_id , group_id , count(*) as conversions  from conversion
    group by job_id , date(ts) , hour(ts) , publisher_id , campaign_id , group_id """)
    return conversion_output 
    
def calculating_qualified(df):    
    qualified_data = df.filter(df.custom_track == 'qualified')
    qualified_data = qualified_data.na.fill({'job_id':0})
    qualified_data = qualified_data.na.fill({'publisher_id':0})
    qualified_data = qualified_data.na.fill({'group_id':0})
    qualified_data = qualified_data.na.fill({'campaign_id':0})
    qualified_data.registerTempTable('qualified')
    qualified_output = spark.sql("""select job_id , date(ts) as date , hour(ts) as hour , publisher_id , campaign_id , group_id , count(*) as qualified  from qualified
    group by job_id , date(ts) , hour(ts) , publisher_id , campaign_id , group_id """)
    return qualified_output
    
def calculating_unqualified(df):
    unqualified_data = df.filter(df.custom_track == 'unqualified')
    unqualified_data = unqualified_data.na.fill({'job_id':0})
    unqualified_data = unqualified_data.na.fill({'publisher_id':0})
    unqualified_data = unqualified_data.na.fill({'group_id':0})
    unqualified_data = unqualified_data.na.fill({'campaign_id':0})
    unqualified_data.registerTempTable('unqualified')
    unqualified_output = spark.sql("""select job_id , date(ts) as date , hour(ts) as hour , publisher_id , campaign_id , group_id , count(*) as unqualified  from unqualified
    group by job_id , date(ts) , hour(ts) , publisher_id , campaign_id , group_id """)
    return unqualified_output
    
def process_final_data(clicks_output,conversion_output,qualified_output,unqualified_output):
    final_data = clicks_output.join(conversion_output,['job_id','date','hour','publisher_id','campaign_id','group_id'],'full').\
    join(qualified_output,['job_id','date','hour','publisher_id','campaign_id','group_id'],'full').\
    join(unqualified_output,['job_id','date','hour','publisher_id','campaign_id','group_id'],'full')
    return final_data 
    
def process_cassandra_data(df):
    clicks_output = calculating_clicks(df)
    conversion_output = calculating_conversion(df)
    qualified_output = calculating_qualified(df)
    unqualified_output = calculating_unqualified(df)
    final_data = process_final_data(clicks_output,conversion_output,qualified_output,unqualified_output)
    return final_data
    
def retrieve_company_data(url,driver,user,password):
    sql = """(SELECT id as job_id, company_id, group_id, campaign_id FROM job) test"""
    company = spark.read.format('jdbc').options(url=url, driver=driver, dbtable=sql, user=user, password=password).load()
    return company 
    
def import_to_mysql(output):
    final_output = output.select('job_id','date','hour','publisher_id','company_id','campaign_id','group_id','unqualified','qualified','conversions','clicks','bid_set','spend_hour')
    final_output = final_output.withColumnRenamed('date','dates').withColumnRenamed('hour','hours').withColumnRenamed('qualified','qualified_application').\
    withColumnRenamed('unqualified','disqualified_application').withColumnRenamed('conversions','conversion')
    final_output = final_output.withColumn('sources',lit('Cassandra'))
    final_output.write.format("jdbc") \
    .option("driver","com.mysql.cj.jdbc.Driver") \
    .option("url", "jdbc:mysql://localhost:3306/data_engineering") \
    .option("dbtable", "events") \
    .mode("append") \
    .option("user", "root") \
    .option("password", "1") \
    .save()
    return print('Data imported successfully')



def main_task(mysql_time):
    host = 'localhost'
    port = '3306'
    db_name = 'data_engineering'
    user = 'root'
    password = '1'
    url = 'jdbc:mysql://' + host + ':' + port + '/' + db_name
    driver = "com.mysql.cj.jdbc.Driver"
    df = spark.read.format("org.apache.spark.sql.cassandra").options(table="tracking",keyspace="study_de").load().where(col('ts')>= mysql_time)
    df = df.select('ts','job_id','custom_track','bid','campaign_id','group_id','publisher_id')
    df = df.filter(df.job_id.isNotNull())
#   process_df = process_df(df)
    cassandra_output = process_cassandra_data(df)
    company = retrieve_company_data(url,driver,user,password)
    final_output = cassandra_output.join(company,'job_id','left').drop(company.group_id).drop(company.campaign_id)
    import_to_mysql(final_output)
    return print('Task Finished')
    
    

def get_latest_time_cassandra():
    data = spark.read.format("org.apache.spark.sql.cassandra").options(table = 'tracking',keyspace = 'study_de').load()
    cassandra_latest_time = data.agg({'ts':'max'}).take(1)[0][0]
    return cassandra_latest_time

def get_mysql_latest_time(url,driver,user,password):    
    sql = """(select max(lastest_update_time) from events) data"""
    mysql_time = spark.read.format('jdbc').options(url=url, driver=driver, dbtable=sql, user=user, password=password).load()
    mysql_time = mysql_time.take(1)[0][0]
    if mysql_time is None:
        mysql_latest = '1998-01-01 23:59:59'
    else :
        mysql_latest = mysql_time.strftime('%Y-%m-%d %H:%M:%S')
    return mysql_latest 
    
    

host = 'localhost'
port = '3306'
db_name = 'data_engineering'
user = 'root'
password = '1'
url = 'jdbc:mysql://' + host + ':' + port + '/' + db_name
driver = "com.mysql.cj.jdbc.Driver"
while True :
    cassandra_time = get_latest_time_cassandra()
    mysql_time = get_mysql_latest_time(url,driver,user,password)
    if cassandra_time > mysql_time : 
        main_task(mysql_time)
    else :
        print("No new data found")
    time.sleep(60)
    






 
