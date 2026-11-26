# kafka3.6.1搭建

## 1、上传解压配置环境变量

```shell
# 配置环境变量
vim  /etc/profile

export KAFKA_HOME=/usr/local/soft/kafka-3.6.1
export PATH=$PATH:$KAFKA_HOME/bin

source /etc/profile
```

## 2、修改配置文件((已改好，可省略)

```shell
cd /usr/local/soft/kafka-3.6.1/config
server.properties
zookeeper.properties
```

## 3、启动

```shell
# 启动zookeeper
zookeeper-server-start.sh -daemon /usr/local/soft/kafka-3.6.1/config/zookeeper.properties

# 启动kafka
kafka-server-start.sh -daemon /usr/local/soft/kafka-3.6.1/config/server.properties
```

## 4、测试

```shell
# 1、创建topic
# topic用于区分不同的数据
kafka-topics.sh --bootstrap-server master:9092 --create --topic students --partitions 1

# 2、或topic列表
kafka-topics.sh --bootstrap-server master:9092 --list 

# 3、生产数据
kafka-console-producer.sh --broker-list master:9092 --topic students

# 4、消费数据
kafka-console-consumer.sh --bootstrap-server master:9092 --from-beginning --topic students
```

