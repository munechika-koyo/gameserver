DROP TABLE IF EXISTS `user`;
CREATE TABLE `user` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `name` varchar(255) DEFAULT NULL,
  `token` varchar(255) DEFAULT NULL,
  `leader_card_id` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `token` (`token`)
);

DROP TABLE IF EXISTS `room`;
CREATE TABLE `room` (
  `room_id` bigint NOT NULL AUTO_INCREMENT,
  `live_id` bigint NOT NULL,
  `joined_user_count` int NOT NULL,
  `max_user_count` int NOT NULL,
  PRIMARY KEY (`room_id`)
);

-- TODO: 外部キー制約を貼る
DROP TABLE IF EXISTS `room_member`;
CREATE TABLE `room_member` (
  `room_member_id` bigint NOT NULL AUTO_INCREMENT,
  `room_id` bigint NOT NULL,
  `user_id` bigint NOT NULL,
  PRIMARY KEY (`room_member_id`)
);

-- testデータ
INSERT INTO `room` SET `live_id`=1001, `joined_user_count`=2, `max_user_count`=4;
INSERT INTO `room` SET `live_id`=1002, `joined_user_count`=1, `max_user_count`=4; 
