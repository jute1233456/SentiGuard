package com.sentiguard.backend.common;

import java.util.List;

import lombok.Data;

@Data
public class PageResult<T> {

    private long total;

    private long pageNum;

    private long pageSize;

    private long pages;

    private List<T> records;

    public static <T> PageResult<T> of(long total, long pageNum, long pageSize, List<T> records) {
        PageResult<T> result = new PageResult<>();
        result.setTotal(total);
        result.setPageNum(pageNum);
        result.setPageSize(pageSize);
        result.setPages(pageSize <= 0 ? 0 : (total + pageSize - 1) / pageSize);
        result.setRecords(records);
        return result;
    }
}
