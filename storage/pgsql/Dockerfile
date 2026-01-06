FROM postgres:16-alpine

# 设置时区
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 设置默认编码
ENV LANG=zh_CN.UTF-8
ENV LC_ALL=zh_CN.UTF-8

# 创建数据目录
RUN mkdir -p /var/lib/postgresql/data && \
    chown -R postgres:postgres /var/lib/postgresql/data

# 使用默认的入口点和命令
CMD ["postgres"]
